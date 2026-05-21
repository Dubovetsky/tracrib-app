import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Download, FileAudio, RefreshCw, Upload } from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

type JobStatus = "queued" | "processing" | "completed" | "failed";

type Job = {
  id: string;
  original_filename: string;
  status: JobStatus;
  error: string | null;
  expected_speaker_count: number | null;
  diarization_status: string | null;
  raw_speaker_count: number | null;
  speaker_count: number | null;
  warnings?: string[];
  timings?: Record<string, number>;
  diagnostics_json_path?: string | null;
  diarization_turns_path?: string | null;
  segments_json_path?: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
};

function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [expectedSpeakers, setExpectedSpeakers] = useState("3");
  const [result, setResult] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [message, setMessage] = useState("");

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? jobs[0] ?? null,
    [jobs, selectedJobId],
  );

  async function loadJobs() {
    const response = await fetch(`${API_BASE}/api/jobs`);
    if (!response.ok) throw new Error("Не удалось загрузить историю");
    const data = (await response.json()) as Job[];
    setJobs(data);
    if (!selectedJobId && data.length > 0) setSelectedJobId(data[0].id);
  }

  async function loadResult(jobId: string) {
    const response = await fetch(`${API_BASE}/api/jobs/${jobId}/result`);
    if (response.status === 409) {
      setResult("");
      return;
    }
    if (!response.ok) throw new Error("Не удалось загрузить результат");
    setResult(await response.text());
  }

  async function submitUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedFile) return;
    setIsUploading(true);
    setMessage("");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const parsedExpectedSpeakers = Number.parseInt(expectedSpeakers, 10);
      if (Number.isInteger(parsedExpectedSpeakers) && parsedExpectedSpeakers > 0) {
        formData.append("expected_speakers", String(parsedExpectedSpeakers));
      }
      const response = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("Загрузка не удалась");
      const job = (await response.json()) as Job;
      setSelectedJobId(job.id);
      setSelectedFile(null);
      setMessage("Файл принят в обработку");
      await loadJobs();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Ошибка загрузки");
    } finally {
      setIsUploading(false);
    }
  }

  useEffect(() => {
    loadJobs().catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      loadJobs().catch((error) => setMessage(error.message));
    }, 3000);
    return () => window.clearInterval(interval);
  }, [selectedJobId]);

  useEffect(() => {
    if (!selectedJob || selectedJob.status !== "completed") {
      setResult("");
      return;
    }
    loadResult(selectedJob.id).catch((error) => setMessage(error.message));
  }, [selectedJob?.id, selectedJob?.status]);

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <h1>Transcrib App</h1>
          <p>Локальная транскрибация аудио на русском языке</p>
        </div>
        <button className="icon-button" type="button" onClick={() => loadJobs()} title="Обновить">
          <RefreshCw size={18} />
        </button>
      </section>

      <section className="workspace">
        <form className="upload-panel" onSubmit={submitUpload}>
          <label className="dropzone">
            <FileAudio size={28} />
            <span>{selectedFile ? selectedFile.name : "Выберите аудио-файл"}</span>
            <input
              type="file"
              accept="audio/*,video/*,.m4a,.mp3,.wav,.ogg,.flac,.aac,.mp4"
              onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <button className="primary-button" type="submit" disabled={!selectedFile || isUploading}>
            <Upload size={18} />
            {isUploading ? "Загрузка..." : "Загрузить"}
          </button>
          <label className="number-field">
            <span>Ожидаемое число спикеров</span>
            <input
              type="number"
              min="1"
              max="12"
              step="1"
              value={expectedSpeakers}
              onChange={(event) => setExpectedSpeakers(event.target.value)}
            />
          </label>
          {message && <p className="message">{message}</p>}
        </form>

        <aside className="history-panel">
          <h2>История</h2>
          <div className="job-list">
            {jobs.map((job) => (
              <button
                key={job.id}
                className={`job-row ${selectedJob?.id === job.id ? "active" : ""}`}
                type="button"
                onClick={() => setSelectedJobId(job.id)}
              >
                <span className="job-title">{job.original_filename}</span>
                <span className={`status ${job.status}`}>{statusLabel(job.status)}</span>
              </button>
            ))}
            {jobs.length === 0 && <p className="empty">Пока нет обработанных файлов</p>}
          </div>
        </aside>

        <section className="result-panel">
          {selectedJob ? (
            <>
              <div className="result-header">
                <div>
                  <h2>{selectedJob.original_filename}</h2>
                  <p>{statusDescription(selectedJob)}</p>
                </div>
                {selectedJob.status === "completed" && (
                  <div className="download-group">
                    <DownloadLink jobId={selectedJob.id} format="txt" />
                    <DownloadLink jobId={selectedJob.id} format="srt" />
                    <DownloadLink jobId={selectedJob.id} format="vtt" />
                    <DownloadLink jobId={selectedJob.id} format="diagnostics" label="JSON" />
                  </div>
                )}
              </div>
              {selectedJob.status === "completed" && <JobDiagnostics job={selectedJob} />}
              {selectedJob.status === "failed" && <pre className="error-box">{selectedJob.error}</pre>}
              {selectedJob.status === "completed" ? (
                <textarea className="transcript" value={result} readOnly />
              ) : (
                <div className="processing-state">
                  <span className="pulse" />
                  <span>{statusLabel(selectedJob.status)}</span>
                </div>
              )}
            </>
          ) : (
            <div className="processing-state">Загрузите файл, чтобы начать транскрибацию</div>
          )}
        </section>
      </section>
    </main>
  );
}

function JobDiagnostics({ job }: { job: Job }) {
  const warnings = job.warnings ?? [];
  const timings = job.timings ?? {};
  return (
    <div className="diagnostics">
      <span>Diarization: {job.diarization_status ?? "unknown"}</span>
      <span>Expected: {job.expected_speaker_count ?? "auto"}</span>
      <span>Acoustic: {job.raw_speaker_count ?? "unknown"}</span>
      <span>Final labels: {job.speaker_count ?? "unknown"}</span>
      {formatTiming(timings.total_job_seconds) && <span>Total: {formatTiming(timings.total_job_seconds)}</span>}
      {formatTiming(timings.asr_seconds) && <span>ASR: {formatTiming(timings.asr_seconds)}</span>}
      {formatTiming(timings.diarization_seconds) && <span>Diarization: {formatTiming(timings.diarization_seconds)}</span>}
      {warnings.length > 0 && <span className="warning">Warnings: {warnings.length}</span>}
    </div>
  );
}

function DownloadLink({
  jobId,
  format,
  label,
}: {
  jobId: string;
  format: "txt" | "srt" | "vtt" | "diagnostics";
  label?: string;
}) {
  return (
    <a className="download-link" href={`${API_BASE}/api/jobs/${jobId}/download/${format}`}>
      <Download size={15} />
      {label ?? format.toUpperCase()}
    </a>
  );
}

function formatTiming(value: number | undefined) {
  if (value === undefined) return "";
  if (value < 60) return `${value.toFixed(1)}s`;
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
}

function statusLabel(status: JobStatus) {
  return {
    queued: "В очереди",
    processing: "Обработка",
    completed: "Готово",
    failed: "Ошибка",
  }[status];
}

function statusDescription(job: Job) {
  if (job.status === "completed") return `Готово: ${formatDate(job.finished_at ?? job.updated_at)}`;
  if (job.status === "failed") return "Обработка завершилась ошибкой";
  if (job.status === "processing") return "ffmpeg и faster-whisper выполняются в фоне";
  return "Задача ожидает свободный worker";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
