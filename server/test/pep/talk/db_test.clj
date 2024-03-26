(ns pep.talk.db-test
  (:require
   [clojure.java.io :as io]
   [clojure.test :refer [deftest testing is]]

   [pep.db :as db]
   [pep.handler :as handler]
   [pep.op :as op]))

(deftest handle-analyze-test
  (let [user-dir (System/getProperty "user.dir")

        response (handler/handle {}
                   {:op "v1/analyze_paths"
                    :root-path (.getPath (io/file user-dir "pep.talk"))})]

    (testing "Successful analysis"
      (is (contains? response :success)))))

(deftest select-under-caret-test
  (let [user-dir (System/getProperty "user.dir")

        root-path (io/file user-dir "pep.talk")

        reference-clj-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "reference.clj"))

        reference-clj-json (db/cache-json-file root-path reference-clj-filename)]

    (is (= #{{:_semantic "keywords"
              :keys-destructuring-ns-modifier true
              :ns "person"}}
          (into #{}
            (map #(select-keys % [:_semantic :ns :keys-destructuring-ns-modifier]))
            (with-open [conn (db/conn)]
              (db/select-under-caret conn reference-clj-json
                {:filename reference-clj-filename
                 :row 15
                 :col 14})))))

    (testing "Two 'definitions' at the same location"
      (is (= #{"locals" "keywords"}
            (into #{}
              (map :_semantic)
              (with-open [conn (db/conn)]
                (db/select-under-caret conn reference-clj-json
                  {:filename reference-clj-filename
                   :row 15
                   :col 22}))))))

    (testing "Keys destructuring"

      ;; Test `foo/bar` keys-destructuring
      ;; Example:
      #_(fn [{:keys [foo/bar]}]
          bar)

      (is (= #{{:_semantic "locals"
                :keys-destructuring nil
                :keys-destructuring-ns-modifier nil
                :name "bar"
                :ns nil}
               {:_semantic "keywords"
                :keys-destructuring true
                :keys-destructuring-ns-modifier nil
                :name "bar"
                :ns "foo"}}
            (into #{}
              (map #(select-keys % [:_semantic :ns :name :keys-destructuring :keys-destructuring-ns-modifier]))
              (with-open [conn (db/conn)]
                (db/select-under-caret conn reference-clj-json
                  {:filename reference-clj-filename
                   :row 20
                   :col 18})))))

      ;; Test `:foo/keys` keys-destructuring-ns-modifier
      ;; Example:
      #_(fn [{:foo/keys [bar]}]
          bar)

      (is (= #{{:_semantic "keywords"
                :keys-destructuring nil
                :keys-destructuring-ns-modifier true
                :ns "foo"
                :name "keys"}}
            (into #{}
              (map #(select-keys % [:_semantic :ns :name :keys-destructuring :keys-destructuring-ns-modifier]))
              (with-open [conn (db/conn)]
                (db/select-under-caret conn reference-clj-json
                  {:filename reference-clj-filename
                   :row 23
                   :col 8}))))))))
