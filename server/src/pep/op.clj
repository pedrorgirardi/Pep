(ns pep.op
  (:require
   [clojure.java.io :as io]
   [clojure.data.json :as json]

   [pep.db :as db]
   [pep.ana :as ana]))

(def xform-kv-not-nillable
  (map
    (fn [m]
      (into {} (remove (comp nil? val)) m))))

(def comp-filename-row-col
  "Comparator to sort by `:filename`, `row` and `col`."
  (juxt :filename :row :col))

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

(defn caret*
  [conn root-path {:keys [filename row col]}]
  (let [cache-file (db/cache-json-file root-path filename)

        row-data (db/select-row conn cache-file {:row row})]
    (reduce
      (fn [acc data]
        (let [start (or (:name-col data) (:col data))
              end (or (:name-end-col data) (:end-col data))]
          (if (<= start col end)
            (conj acc data)
            acc)))
      #{}
      row-data)))

(defn persist-analysis!
  [root-path {:keys [analysis]}]
  (let [cache-dir (db/cache-dir root-path)]

    (when-not (.exists cache-dir)
      (.mkdirs cache-dir))

    (doseq [[filename analysis] (ana/index analysis)]
      (let [f (io/file cache-dir (db/filename-cache filename))]
        (spit f (json/write-str analysis))))))

(defn v1-analyze_paths
  [_context {:keys [root-path]}]
  (let [result (ana/analyze-paths! root-path)]

    (persist-analysis! root-path result)

    (ana/diagnostics* result)))

(defn v1-analyze_text
  [_context {:keys [root-path filename text]}]
  (let [^java.util.Base64$Decoder decoder (java.util.Base64/getDecoder)

        bytes (.decode decoder ^String text)

        result (ana/analyze-text!
                 {:text (String. bytes "UTF-8")
                  :filename (or filename "-")})]

    (persist-analysis! root-path result)

    (ana/diagnostics* result)))

(defn v1-diagnostics
  [_context {:keys [root-path]}]
  (ana/diagnostics root-path))

(defn v1-under-caret
  [{:keys [conn]} {:keys [root-path filename row col]}]
  (caret* conn root-path
    {:filename filename
     :row row
     :col col}))

(defn v1-namespaces
  [{:keys [conn]} {:keys [root-path]}]
  (let [namespaces (db/select-namespaces conn (db/cache-*json-file root-path))
        namespaces (into #{} namespaces)
        namespaces (sort-by comp-filename-row-col namespaces)]

    namespaces))

(defn  v1-find_definitions
  [{:keys [conn]} {:keys [root-path filename row col]}]
  (when-let [prospect (caret conn root-path
                        {:filename filename
                         :row row
                         :col col})]
    (let [dir (db/cache-dir root-path)

          definitions (db/select-definitions conn dir prospect)
          definitions (into #{} xform-kv-not-nillable definitions)
          definitions (sort-by comp-filename-row-col definitions)]

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
          references (sort-by comp-filename-row-col references)]

      references)))