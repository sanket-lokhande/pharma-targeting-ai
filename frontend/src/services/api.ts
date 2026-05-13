import axios from "axios";
import type { AnalyzeRequest, AnalyzeResponse, SavedConfiguration, UploadResponse } from "../types";

const api = axios.create({
  baseURL: "http://127.0.0.1:8000"
});

export async function uploadCurrent(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  
  const response = await fetch("http://127.0.0.1:8000/api/upload/current", {
    method: "POST",
    body: formData
  });
  
  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Upload failed: ${response.status} ${error}`);
  }
  
  return response.json();
}

export async function uploadPrevious(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  
  const response = await fetch("http://127.0.0.1:8000/api/upload/previous", {
    method: "POST",
    body: formData
  });
  
  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Upload failed: ${response.status} ${error}`);
  }
  
  return response.json();
}

export async function analyze(payload: AnalyzeRequest): Promise<AnalyzeResponse> {
  const { data } = await api.post<AnalyzeResponse>("/api/analyze", payload);
  return data;
}

export function exportAnalysis(analysisId: string): string {
  return `${api.defaults.baseURL}/api/export/${analysisId}`;
}

export async function saveConfiguration(payload: SavedConfiguration): Promise<void> {
  await api.post("/api/configurations", payload);
}

export async function listConfigurations(): Promise<SavedConfiguration[]> {
  const { data } = await api.get<SavedConfiguration[]>("/api/configurations");
  return data;
}
