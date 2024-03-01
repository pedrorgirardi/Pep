(ns pep.ana
  (:require
   [clojure.java.io :as io]
   [clojure.tools.deps :as deps]
   [clojure.tools.build.api :as b]

   [clj-kondo.core :as clj-kondo]))

(def paths-config
  {:skip-lint true

   :analysis
   {:var-definitions true
    :var-usages true
    :arglists true
    :locals true
    :keywords true
    :symbols true
    :java-class-definitions false
    :java-class-usages true
    :java-member-definitions false
    :instance-invocations true}

   :output
   {:canonical-paths true}})

(defn slurp-deps
  "Slurp deps.edn from `root-path`."
  [root-path]
  (deps/slurp-deps (io/file root-path "deps.edn")))

(defn deps-paths
  "Returns a vector containing paths and extra-paths."
  [deps-map]
  (reduce-kv
    (fn [paths _ {:keys [extra-paths]}]
      (into paths extra-paths))
    (:paths deps-map)
    (:aliases deps-map)))

(defn project-paths
  [root-path]
  (into #{}
    (map #(io/file root-path %))
    (some-> root-path
      (slurp-deps)
      (deps-paths))))

(defn project-classpath-basis
  [root-path]
  (when-let [deps-map (slurp-deps root-path)]
    (binding [b/*project-root* root-path]
      (b/create-basis {:projet deps-map}))))

(defn mkdir-clj-kondo-cache!
  "Creates a .clj-kondo directory at `root-path` if it doesn't exist."
  [root-path]
  (let [dir (io/file root-path ".clj-kondo")]
    (when-not (.exists dir)
      (.mkdir dir))))

(defn analyze-paths!
  "Analyze paths with clj-kondo."
  ([root-path]
   (analyze-paths! paths-config root-path))
  ([config root-path]
   (let [paths (project-paths root-path)]
     (when (seq paths)
       ;; Note:
       ;; Analysis doesn't work without a `.clj-kondo` directory.
       (mkdir-clj-kondo-cache! root-path)

       (clj-kondo/run!
         {:lint paths
          :parallel true
          :config config})))))

(defn diagnostics
  [root-path]
  (let [{:keys [findings summary]} (analyze-paths!
                                     {:skip-lint true
                                      :output {:canonical-paths true}}
                                     root-path)]
    {:diagnostics (group-by :level findings)
     :summary summary}))


(comment

  (diagnostics ".")

  )
