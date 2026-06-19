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

// --- Lot 2 : alignement de chevauchement ---
export const listDatasetReads = (datasetId, params) =>
    api.get(`/datasets/${datasetId}/reads/`, { params });
export const getDatasetRead = (datasetId, index) =>
    api.get(`/datasets/${datasetId}/reads/${index}/`);
export const createAlignment = (payload) => api.post("/alignments/", payload);
export const listAlignments = () => api.get("/alignments/");
export const getAlignment = (id) => api.get(`/alignments/${id}/`);

// --- Lot 3 : assemblage de novo ---
export const createAssembly = (payload) => api.post("/assemblies/", payload);
export const listAssemblies = () => api.get("/assemblies/");
export const getAssembly = (id) => api.get(`/assemblies/${id}/`);
export const assemblyContigsUrl = (id) =>
    `${api.defaults.baseURL}/assemblies/${id}/contigs.fasta/`;

export default api;
