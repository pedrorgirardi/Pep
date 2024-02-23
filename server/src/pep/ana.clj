(ns pep.ana
  (:require
   [clojure.java.io :as io]
   [clojure.tools.deps :as deps]
   [clojure.tools.build.api :as build]

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

(def classpath-config
  {:skip-lint true

   :analysis
   {:var-definitions {:shallow true}
    :var-usages false
    :arglists true
    :keywords true
    :java-class-definitions false}

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

(defn mkdir-clj-kondo-cache!
  "Creates a .clj-kondo directory at `project_path` if it doesn't exist."
  [project_path]
  (let [dir (io/file project_path ".clj-kondo")]
    (when-not (.exists dir)
      (.mkdir dir))))

(defn analyze-paths!
  "Analyze paths with clj-kondo."
  [project_path]
  (let [paths (project-paths project_path)]
    (when (seq paths)
      ;; Note:
      ;; Analysis doesn't work without a `.clj-kondo` directory.
      (mkdir-clj-kondo-cache! project_path)

      (clj-kondo/run!
        {:lint paths
         :parallel true
         :config paths-config}))))

(defn analyze-classpath!
  "Analyze classpath with clj-kondo."
  [project_path]
  (when-let [deps-map (slurp-deps project_path)]
    (let [basis (binding [build/*project-root* project_path]
                  (build/create-basis {:projet deps-map}))]

      ;; Note:
      ;; Analysis doesn't work without a `.clj-kondo` directory.
      (mkdir-clj-kondo-cache! project_path)

      (clj-kondo/run!
        {:lint (:classpath-roots basis)
         :config classpath-config}))))


(comment

  (def paths-result (analyze-paths! "/Users/pedro/Developer/data90"))

  (:summary paths-result)
  (:findings paths-result)


  (def classpath-result (analyze-classpath! "/Users/pedro/Developer/data90"))

  (:summary classpath-result)

  ;; Warnings"
  (into []
    (filter #(= :warning (:level %)))
    (:findings classpath-result))

  ;; Errors:
  (into []
    (filter #(= :error (:level %)))
    (:findings classpath-result))


  )
