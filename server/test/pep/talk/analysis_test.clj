(ns pep.talk.analysis-test
  (:require
   [clojure.java.io :as io]

   [clj-kondo.core :as clj-kondo]

   [pep.ana :as ana]))

(comment

  (require '[tab.api :as tab])

  (def tab (tab/run :browse? true))

  (tab/halt tab)


  (let [user-dir (System/getProperty "user.dir")

        talk-dir (io/file user-dir "pep.talk" "src" "pep" "talk")

        {:keys [analysis]} (clj-kondo/run!
                             {:lint [(io/file talk-dir "analysis.clj")]
                              :config ana/paths-config})]

    (tap> analysis))

  )
