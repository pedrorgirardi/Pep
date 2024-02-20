#!/usr/bin/env bb

(require
  '[clojure.test :as t]
  '[babashka.classpath :as cp])

(cp/add-classpath "src:test")

(require
  'pep.sublime-test
  'pep.ana-test)

(let [test-results (t/run-tests
                     'pep.sublime-test
                     'pep.ana-test)

      {:keys [fail error]} test-results]

  (when (pos? (+ fail error))
    (System/exit 1)))
