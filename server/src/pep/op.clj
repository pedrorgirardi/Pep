(ns pep.op
  (:require
   [pep.db :as db]))

(def xform-kv-not-nillable
  (map
    (fn [m]
      (into {} (remove (comp nil? val)) m))))

(defn sort-by-filename-row-col
  "Sort by `:filename`, `row` and `col`."
  [coll]
  (sort-by (juxt :filename :row :col) coll))

(defn caret
  [conn root-path {:keys [filename row col]}]
  (let [cache-file (db/cache-json-file root-path filename)

        row-data (db/select-row conn cache-file {:row row})]
    (reduce
      (fn [_ data]
        (let [start (or (:name-col data) (:col data))
              end (or (:name-end-col data) (:end-col data))]
          (when (<= start col end)
            (reduced data))))
      nil
      row-data)))

(defn  v1-find_definitions
  [{:keys [conn]} {:keys [root-path filename row col]}]
  (when-let [prospect (caret conn root-path
                        {:filename filename
                         :row row
                         :col col})]
    (let [dir (db/cache-dir root-path)

          definitions (db/select-definitions conn dir prospect)
          definitions (into #{} xform-kv-not-nillable definitions)
          definitions (sort-by-filename-row-col definitions)]

      definitions)))

(defn v1-find-references-in-file
  [{:keys [conn]} {:keys [root-path filename row col]}]
  (when-let [prospect (caret conn root-path
                        {:filename filename
                         :row row
                         :col col})]
    (let [cache-file (db/cache-json-file root-path filename)

          references (db/select-references conn cache-file prospect)
          references (into #{} xform-kv-not-nillable references)
          references (sort-by-filename-row-col references)]

      references)))
