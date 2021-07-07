(let [x 1]
  x
  x
  x)

(def a 1)(def b 2)

(defn f "Docstring." [x] x)


(f 1)

(let [a 1] nil)

(let [a 1]
  a
  a)

(let [f (fn f [x] x)]
  (f)
  (f))

(inc "")

(map inc 1)
