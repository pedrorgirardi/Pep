(ns ns2)

(def a 1)

#?(:clj (def foo 1)
   :cljs (def foo 1))

foo
