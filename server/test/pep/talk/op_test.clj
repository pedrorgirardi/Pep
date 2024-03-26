(ns pep.talk.op-test
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

(deftest caret*-test
  (let [user-dir (System/getProperty "user.dir")

        root-path (io/file user-dir "pep.talk")

        reference-clj-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "reference.clj"))]

    (is (= #{{:_semantic "keywords"
              :keys-destructuring-ns-modifier true
              :ns "person"}}
          (into #{}
            (map #(select-keys % [:_semantic :ns :keys-destructuring-ns-modifier]))
            (with-open [conn (db/conn)]
              (op/caret* conn root-path
                {:filename reference-clj-filename
                 :row 15
                 :col 14})))))

    (testing "Two 'definitions' at the same location"
      (is (= #{"locals" "keywords"}
            (into #{}
              (map :_semantic)
              (with-open [conn (db/conn)]
                (op/caret* conn root-path
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
                (op/caret* conn root-path
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
                (op/caret* conn root-path
                  {:filename reference-clj-filename
                   :row 23
                   :col 8}))))))))

(deftest caret-test
  (let [user-dir (System/getProperty "user.dir")

        root-path (io/file user-dir "pep.talk")

        reference-clj-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "reference.clj"))

        common-cljc-filename (.getPath (io/file user-dir "pep.talk" "src" "pep" "talk" "common.cljc"))]

    (testing "reference.clj"
      (is (= nil
            (with-open [conn (db/conn)]
              (op/caret conn root-path
                {:filename reference-clj-filename
                 :row 2
                 :col 2}))))

      (is (= {:_semantic "keywords"
              :ns "person"
              :name "name"
              :row 11
              :col 1}
            (select-keys
              (with-open [conn (db/conn)]
                (op/caret conn root-path
                  {:filename reference-clj-filename
                   :row 11
                   :col 11}))
              [:ns :name :_semantic :row :col])))

      (is (= {:_semantic "locals"
              :name "age"
              :row 15
              :col 21}
            (select-keys
              (with-open [conn (db/conn)]
                (op/caret conn root-path
                  {:filename reference-clj-filename
                   :row 15
                   :col 22}))
              [:name :_semantic :row :col])))

      (is (= {:name "x"
              :_semantic "var-usages"
              :row 7
              :col 11}
            (select-keys
              (with-open [conn (db/conn)]
                (op/caret conn root-path
                  {:filename reference-clj-filename
                   :row 7
                   :col 11}))
              [:name :_semantic :row :col])))

      (is (= {:name "y"
              :_semantic "var-usages"
              :row 7
              :col 13}
            (select-keys
              (with-open [conn (db/conn)]
                (op/caret conn root-path
                  {:filename reference-clj-filename
                   :row 7
                   :col 13}))
              [:name :_semantic :row :col])))

      (is (= {:name "b"
              :_semantic "locals"
              :row 9
              :col 11}
            (select-keys
              (with-open [conn (db/conn)]
                (op/caret conn root-path
                  {:filename reference-clj-filename
                   :row 9
                   :col 11}))
              [:name :_semantic :row :col]))))

    (is (= {:name "a"
            :_semantic "local-usages"
            :row 9
            :col 19}
          (select-keys
            (with-open [conn (db/conn)]
              (op/caret conn root-path
                {:filename reference-clj-filename
                 :row 9
                 :col 19}))
            [:name :_semantic :row :col])))

    (testing "common.cljc"
      (is (= {:name "println"
              :_semantic "var-usages"
              :row 5
              :col 3
              :name-col 4}
            (select-keys
              (with-open [conn (db/conn)]
                (op/caret conn root-path
                  {:filename common-cljc-filename
                   :row 5
                   :col 8}))
              [:name :_semantic :row :col :name-col])))

      (is (= {:name "hello"
              :_semantic "var-usages"
              :row 9
              :col 3
              :name-col 4}
            (select-keys
              (with-open [conn (db/conn)]
                (op/caret conn root-path
                  {:filename common-cljc-filename
                   :row 9
                   :col 6}))
              [:name :_semantic :row :col :name-col]))))))
