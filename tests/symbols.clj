;; Problem:
;; Pep finds usages of these symbols in paths,
;; but from a var it doesn't find a symbol.
;;
;; Solution:
;; Searching for usages of symbol or var should
;; also include symbols.

'clojure.core/map

'example/foo

