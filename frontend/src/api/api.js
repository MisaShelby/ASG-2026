import axios from "axios";

const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL,
});

// --- Q1 : Datasets, qualité, conversion ---
export const listDatasets = () => api.get("/datasets/");
export const getDataset = (id) => api.get(`/datasets/${id}/`);
export const uploadDataset = (formData) =>
    api.post("/datasets/", formData, {
        headers: { "Content-Type": "multipart/form-data" },
    });
export const getQualityReport = (id) => api.get(`/datasets/${id}/quality/`);
export const convertToFasta = (id, params) =>
    api.post(`/datasets/${id}/convert/`, params);
export const listConversions = (datasetId) =>
    api.get("/conversions/", { params: { dataset: datasetId } });

// --- Q2 : découpage k-mers ---
export const runKmerAnalysis = (id, params) =>
    api.post(`/datasets/${id}/kmers/`, params);
export const getKmerAnalysis = (id) => api.get(`/kmer-analyses/${id}/`);
export const getTopKmers = (id) => api.get(`/kmer-analyses/${id}/top/`);

// --- Q3 : spectre / histogramme ---
export const getKmerSpectrum = (id) => api.get(`/kmer-analyses/${id}/spectrum/`);

export default api;
