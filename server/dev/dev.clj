(ns dev
  (:require
   [clojure.java.io :as io]
   [clojure.pprint :as pprint]

   [next.jdbc :as jdbc]

   [pep.db :as db]))

(comment

  @(def root-path (.getParent (io/file (System/getProperty "user.dir"))))

  @(def filename (.getPath (io/file root-path ".pep" "*.json")))

  (defn summarize [sqlparams]
    (pprint/print-table [:column_name :column_type :null_percentage]
      (sort-by :null_percentage
        (into []
          (map #(select-keys % [:column_name :column_type :null_percentage]))
          (with-open [conn (db/conn)]
            (jdbc/execute! conn sqlparams))))))

  (summarize
    [(format "SUMMARIZE SELECT * FROM read_json_auto('%s', format='array')"
       filename)])

  (summarize
    [(format "SUMMARIZE SELECT * FROM read_json_auto('%s', format='array') WHERE _semantic = 'var-definitions'"
       filename)])

  (summarize
    [(format "SUMMARIZE SELECT * FROM read_json_auto('%s', format='array') WHERE _semantic = 'var-usages'"
       filename)])
  

  )
