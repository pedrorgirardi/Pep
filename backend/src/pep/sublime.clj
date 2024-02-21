(ns pep.sublime
  (:require
   [clojure.java.io :as io]
   [clojure.stacktrace :as stacktrace]
   [clojure.tools.deps :as deps]
   [clojure.tools.build.api :as b]

   [clj-kondo.core :as clj-kondo]

   [pep.ana :as ana]))

(def lint-config
  {:analysis
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

(defn project-paths [project_path]
  (into #{}
    (map #(io/file project_path %))
    (some-> project_path (slurp-deps) (deps-paths))))

(defn mkdir-clj-kondo-cache!
  "Creates a .clj-kondo directory at `project_path` if it doesn't exist."
  [project_path]
  (let [dir (io/file project_path ".clj-kondo")]
    (when-not (.exists dir)
      (.mkdir dir))))

(defn analyze-paths!
  "Analyze paths with clj-kondo."
  [{:keys [project_base_name project_path]}]
  (let [paths (project-paths project_path)]
    (when (seq paths)
      ;; Note:
      ;; Analysis doesn't work without a `.clj-kondo` directory.
      (mkdir-clj-kondo-cache! project_path)

      (let [result (clj-kondo/run!
                     {:lint paths
                      :parallel true
                      :config lint-config})]

        (ana/dbsave! project_base_name result)))))

(defn analyze-classpath!
  "Analyze classpath with clj-kondo."
  [{:keys [project_base_name project_path]}]
  (when-let [deps-map (slurp-deps project_path)]
    (when-let [basis (binding [b/*project-root* project_path]
                       (try
                         (b/create-basis {:projet deps-map})
                         (catch Exception ex
                           (binding [*out* *err*]
                             (stacktrace/print-stack-trace ex))

                           nil)))]
      (let [result (clj-kondo/run!
                     {:lint (:classpath-roots basis)
                      :config ana/lint-config})]

        (ana/dbsave! project_base_name result)))))


(comment

  (analyze-paths!
    {:project_base_name "data90"
     :project_path "/Users/pedro/Developer/data90"})

  (analyze-paths!
    {:project_base_name "rex.system"
     :project_path "/Users/pedro/Developer/Velos/rex.system/rex.ingestion"})


  (analyze-classpath!
    {:project_base_name "data90"
     :project_path "/Users/pedro/Developer/data90"})

  (analyze-classpath!
    {:project_base_name "rex.system"
     :project_path "/Users/pedro/Developer/Velos/rex.system"})

  )
