(ns dev
  (:require
   [clojure.java.io :as io]
   [clojure.pprint :as pprint]

   [tab.api :as tab]
   [next.jdbc :as jdbc]
   [clj-kondo.core :as clj-kondo]

   [pep.ana :as ana]
   [pep.db :as db]))

(comment

  (def tab (tab/run :browse? true))

  (tab/halt tab)


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


  (let [user-dir (System/getProperty "user.dir")

        talk-dir (io/file user-dir "pep.talk" "src" "pep" "talk")

        {:keys [analysis]} (clj-kondo/run!
                             {:lint [(io/file talk-dir "analysis.clj")]
                              :config ana/view-config})]

    (tap> analysis))
  

  )
