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
  "Slurp deps.edn from `project_path`."
  [project_path]
  (deps/slurp-deps (io/file project_path "deps.edn")))

(defn deps-paths
  "Returns a vector containing paths and extra-paths."
  [deps-map]
  (reduce-kv
    (fn [paths _ {:keys [extra-paths]}]
      (into paths extra-paths))
    (:paths deps-map)
    (:aliases deps-map)))

(defn project-paths
  [project_path]
  (into #{}
    (map #(io/file project_path %))
    (some-> project_path
      slurp-deps
      deps-paths)))

(defn project-classpath-basis
  [project_path]
  (when-let [deps-map (slurp-deps project_path)]
    (binding [b/*project-root* project_path]
      (b/create-basis {:projet deps-map}))))

(defn mkdir-clj-kondo-cache!
  "Creates a .clj-kondo directory at `project_path` if it doesn't exist."
  [project_path]
  (let [dir (io/file project_path ".clj-kondo")]
    (when-not (.exists dir)
      (.mkdir dir))))

(defn analyze-paths!
  "Analyze paths with clj-kondo."
  ([project_path]
   (analyze-paths! paths-config project_path))
  ([config project_path]
   (let [paths (project-paths project_path)]
     (when (seq paths)
       ;; Note:
       ;; Analysis doesn't work without a `.clj-kondo` directory.
       (mkdir-clj-kondo-cache! project_path)

       (clj-kondo/run!
         {:lint paths
          :parallel true
          :config config})))))

(defn diagnostics
  [project_path]
  (let [{:keys [findings summary]} (analyze-paths!
                                     {:skip-lint true
                                      :output {:canonical-paths true}}
                                     project_path)]
    {:diagnostics (group-by :level findings)
     :summary summary}))


(comment

  (def paths-result (analyze-paths! "/Users/pedro/Developer/data90"))

  (diagnostics "/Users/pedro/Developer/data90")


  )
