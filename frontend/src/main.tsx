import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { AlertCircle, CircleStop, Download, FileAudio, RefreshCw, Upload, X } from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

type JobStatus = "queued" | "processing" | "completed" | "failed";
type MessageType = "success" | "error" | "info" | "processing";

type Job = {
  id: string;
  original_filename: string;
  status: JobStatus;
  error: string | null;
  expected_speaker_count: number | null;
  asr_quality: string | null;
  audio_profile: string | null;
  source_duration_seconds: number | null;
  estimated_total_seconds: number | null;
  processing_stage: string | null;
  progress_percent: number | null;
  progress_message: string | null;
  diarization_status: string | null;
  raw_speaker_count: number | null;
  speaker_count: number | null;
  warnings?: string[];
  timings?: Record<string, number>;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
};

type PerformanceProfile = {
  hardware: {
    cpu_count: number;
    cuda_available: boolean;
    gpu_name: string | null;
    estimate_source: string;
  };
  calibrated_samples: number;
  one_hour_estimates_seconds: Record<string, Record<string, number | null>>;
};

function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [asrQuality, setAsrQuality] = useState("maximum");
  const [result, setResult] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [uploadState, setUploadState] = useState<MessageType>("info");
  const [uploadStatus, setUploadStatus] = useState("");
  const [performanceProfile, setPerformanceProfile] = useState<PerformanceProfile | null>(null);

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? jobs[0] ?? null,
    [jobs, selectedJobId],
  );
  const sidebarStatus = useMemo(
    () => currentSidebarStatus(selectedFile, isUploading, uploadStatus, uploadState, selectedJob),
    [selectedFile, isUploading, uploadStatus, uploadState, selectedJob],
  );

  async function loadJobs() {
    const response = await fetch(`${API_BASE}/api/jobs`);
    if (!response.ok) throw new Error("Не удалось загрузить историю");
    const data = (await response.json()) as Job[];
    setJobs(data);
    if (!selectedJobId && data.length > 0) setSelectedJobId(data[0].id);
  }

  async function loadPerformanceProfile() {
    const response = await fetch(`${API_BASE}/api/performance-profile`);
    if (!response.ok) return;
    setPerformanceProfile((await response.json()) as PerformanceProfile);
  }

  async function refreshJobs() {
    setIsRefreshing(true);
    try {
      await Promise.all([loadJobs(), loadPerformanceProfile()]);
      if (selectedJob?.status === "completed") await loadResult(selectedJob.id);
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Ошибка обновления", "error");
    } finally {
      window.setTimeout(() => setIsRefreshing(false), 650);
    }
  }

  async function cancelSelectedJob() {
    if (!selectedJob || !canCancelJob(selectedJob)) return;
    setIsCancelling(true);
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${selectedJob.id}/cancel`, { method: "POST" });
      if (!response.ok) throw new Error("Не удалось прервать обработку");
      showMessage("Обработка прервана", "error");
      await loadJobs();
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Не удалось прервать обработку", "error");
    } finally {
      setIsCancelling(false);
    }
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

  function showMessage(text: string, type: MessageType) {
    if (text) {
      setUploadStatus(text);
      setUploadState(type);
    }
  }

  function selectHistoryJob(jobId: string) {
    setSelectedJobId(jobId);
    setSelectedFile(null);
    setUploadStatus("");
    setUploadState("info");
  }

  async function submitUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedFile) return;
    setIsUploading(true);
    showMessage("", "info");
    setUploadStatus("Загружаем файл");
    setUploadState("info");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("asr_quality", apiQualityValue(asrQuality));
      const response = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("Загрузка не удалась");
      const job = (await response.json()) as Job;
      setSelectedJobId(job.id);
      setSelectedFile(null);
      showMessage("Обработка запущена", "processing");
      await Promise.all([loadJobs(), loadPerformanceProfile()]);
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Ошибка загрузки", "error");
    } finally {
      setIsUploading(false);
    }
  }

  async function deleteJob(jobId: string) {
    const response = await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: "DELETE" });
    if (!response.ok) {
      showMessage("Не удалось удалить запись", "error");
      return;
    }
    setJobs((current) => {
      const next = current.filter((job) => job.id !== jobId);
      if (selectedJobId === jobId) setSelectedJobId(next[0]?.id ?? null);
      return next;
    });
    if (selectedJobId === jobId) setResult("");
    showMessage("Запись удалена", "success");
  }

  useEffect(() => {
    loadJobs().catch((error) => showMessage(error.message, "error"));
    loadPerformanceProfile().catch(() => undefined);
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      loadJobs().catch((error) => showMessage(error.message, "error"));
      loadPerformanceProfile().catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(interval);
  }, [selectedJobId]);

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!selectedJob || selectedJob.status !== "completed") {
      setResult("");
      return;
    }
    loadResult(selectedJob.id).catch((error) => showMessage(error.message, "error"));
  }, [selectedJob?.id, selectedJob?.status]);

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <h1>Transcrib App</h1>
          <p>Локальная транскрибация аудио на русском языке</p>
        </div>
        <div className="topbar-actions">
          <button
            className="icon-button interrupt-button"
            type="button"
            onClick={cancelSelectedJob}
            title="Прервать обработку выбранной записи"
            disabled={!selectedJob || !canCancelJob(selectedJob) || isCancelling}
          >
            <CircleStop size={17} />
            <span>Прервать</span>
          </button>
        <button
          className={`icon-button ${isRefreshing ? "refreshing" : ""}`}
          type="button"
          onClick={refreshJobs}
          title="Обновить историю и результат"
          disabled={isRefreshing}
        >
          <RefreshCw size={18} />
        </button>
        </div>
      </section>

      <section className="workspace">
        <form className="upload-panel" onSubmit={submitUpload}>
          <label className="dropzone">
            <FileAudio size={28} />
            <span className="selected-file-name">{selectedFile ? selectedFile.name : "Выберите аудио-файл"}</span>
            <input
              type="file"
              accept="audio/*,video/*,.m4a,.mp3,.wav,.ogg,.flac,.aac,.mp4"
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                setSelectedFile(file);
                if (file) {
                  setUploadStatus("Файл выбран");
                  setUploadState("success");
                } else {
                  setUploadStatus("");
                  setUploadState("info");
                }
              }}
            />
          </label>
          <button className="primary-button" type="submit" disabled={!selectedFile || isUploading}>
            <Upload size={18} />
            {isUploading ? "Загружаем..." : "Запустить обработку"}
          </button>
          <label className="number-field">
            <span>Качество распознавания</span>
            <select value={asrQuality} onChange={(event) => setAsrQuality(event.target.value)}>
              <option value="maximum">Максимальное</option>
              <option value="balanced">Сбалансированное</option>
              <option value="fast">Быстрое</option>
            </select>
          </label>
          <ProfileHelp performanceProfile={performanceProfile} />
          {sidebarStatus && <p className={`upload-status ${sidebarStatus.type}`}>{sidebarStatus.text}</p>}
        </form>

        <aside className="history-panel">
          <h2>История</h2>
          <div className="job-list">
            {jobs.map((job) => (
              <div key={job.id} className={`job-row ${selectedJob?.id === job.id ? "active" : ""}`}>
                <button className="job-select" type="button" onClick={() => selectHistoryJob(job.id)}>
                  <span className="job-title">{job.original_filename}</span>
                  <span className={`status ${job.status}`}>{statusLabel(job.status)}</span>
                </button>
                <button
                  className="delete-job"
                  type="button"
                  onClick={() => deleteJob(job.id)}
                  title="Удалить"
                  aria-label={`Удалить ${job.original_filename}`}
                >
                  <X size={16} />
                </button>
              </div>
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
                  <p className={`job-current-status ${selectedJob.status === "processing" ? "shimmer" : ""}`}>
                    {statusDescription(selectedJob)}
                  </p>
                  <PipelineModules job={selectedJob} />
                  {selectedJob.status === "completed" && (
                    <div className="download-group">
                      <DownloadLink jobId={selectedJob.id} format="txt" />
                      <DownloadLink jobId={selectedJob.id} format="raw-txt" label="RAW" />
                    </div>
                  )}
                </div>
              </div>
              {selectedJob.status === "completed" && <JobDiagnostics job={selectedJob} />}
              {selectedJob.status === "failed" && (
                <div className="failed-state">
                  <AlertCircle size={18} />
                  <div>
                    <strong>Ошибка обработки</strong>
                    {selectedJob.error && <pre className="error-box">{selectedJob.error}</pre>}
                  </div>
                </div>
              )}
              {selectedJob.status === "completed" ? (
                <textarea className={`transcript ${isRefreshing ? "flash" : ""}`} value={result} readOnly />
              ) : selectedJob.status === "processing" || selectedJob.status === "queued" ? (
                <div className="processing-state">
                  <span className="pulse" />
                  <span>{statusLabel(selectedJob.status)}</span>
                  {selectedJob.status === "processing" && <ProcessingEstimate job={selectedJob} now={now} />}
                </div>
              ) : null}
            </>
          ) : (
            <div className="processing-state">Загрузите файл, чтобы начать транскрибацию</div>
          )}
        </section>
      </section>
    </main>
  );
}

function ProfileHelp({
  performanceProfile,
}: {
  performanceProfile: PerformanceProfile | null;
}) {
  const qualityTimes = (quality: string) =>
    formatDuration(
      performanceProfile?.one_hour_estimates_seconds?.[apiQualityValue(quality)]?.[autoAudioProfileForQuality(quality)]
        ?? fallbackOneHourEstimate(quality),
    );
  return (
    <div className="profile-help">
      <h3>Режим распознавания</h3>
      <div className="mode-help-list">
        <p>
          <span className="mode-help-title">Максимальное</span>
          <small><strong>Около {qualityTimes("maximum")}</strong> / 1 час</small>
          <span className="mode-help-note">сложная речь, лучшая точность</span>
        </p>
        <p>
          <span className="mode-help-title">Сбалансированное</span>
          <small><strong>Около {qualityTimes("balanced")}</strong> / 1 час</small>
          <span className="mode-help-note">обычные записи встреч</span>
        </p>
        <p>
          <span className="mode-help-title">Быстрое</span>
          <small><strong>Около {qualityTimes("fast")}</strong> / 1 час</small>
          <span className="mode-help-note">быстрый черновик</span>
        </p>
      </div>
    </div>
  );
}

function currentSidebarStatus(
  selectedFile: File | null,
  isUploading: boolean,
  uploadStatus: string,
  uploadState: MessageType,
  selectedJob: Job | null,
): { text: string; type: MessageType } | null {
  if (isUploading) return { text: "Загружаем файл", type: "info" };
  if (selectedFile) return { text: "Файл выбран", type: "success" };
  if (uploadStatus && uploadState === "error") return { text: uploadStatus, type: "error" };
  if (selectedJob) return jobSidebarStatus(selectedJob);
  return null;
}

function canCancelJob(job: Job) {
  return job.status === "queued" || job.status === "processing";
}

function jobSidebarStatus(job: Job): { text: string; type: MessageType } {
  if (job.status === "completed") return { text: "Обработка завершена", type: "success" };
  if (job.status === "failed") return { text: "Ошибка обработки", type: "error" };
  if (job.status === "queued") return { text: "Ожидает обработки", type: "info" };
  return { text: job.progress_message || stageStatusLabel(job.processing_stage), type: "processing" };
}

function stageStatusLabel(stage: string | null) {
  return {
    starting: "Запускаем обработку",
    preprocess: "Готовим аудио",
    asr: "Распознаем речь",
    diarization: "Разделяем голоса",
    polish: "Собираем текст",
    export: "Готовим файл",
  }[stage ?? ""] ?? "Обработка идет";
}

function ProcessingEstimate({ job, now }: { job: Job; now: number }) {
  const startedAt = job.started_at ? new Date(job.started_at).getTime() : null;
  const elapsed = startedAt ? Math.max(0, (now - startedAt) / 1000) : 0;
  const total = job.estimated_total_seconds ?? estimateFromDuration(job);
  if (!total) return <span className="eta">Оценка времени появится после анализа файла</span>;
  const remaining = Math.max(0, total - elapsed);
  const progress = job.progress_percent ?? Math.min(96, Math.max(4, (elapsed / total) * 100));
  const remainingText =
    remaining < 60 && progress < 97
      ? "время уточняется"
      : `осталось примерно ${formatDuration(remaining)}`;
  return (
    <span className="eta">
      <span>{remainingText}</span>
      <span className="eta-bar"><span style={{ width: `${progress}%` }} /></span>
    </span>
  );
}

function PipelineModules({ job }: { job: Job }) {
  const stages = [
    ["preprocess", "Аудио"],
    ["asr", "Речь"],
    ["diarization", "Голоса"],
    ["polish", "Текст"],
    ["export", "Файл"],
  ] as const;
  const currentIndex = stages.findIndex(([stage]) => stage === job.processing_stage);
  return (
    <div className="module-status" aria-label="Статус модулей обработки">
      {stages.map(([stage, label], index) => {
        const state = moduleState(job, index, currentIndex);
        return (
          <span key={stage} className={`module-pill ${state}`}>
            {label}
          </span>
        );
      })}
    </div>
  );
}

function moduleState(job: Job, index: number, currentIndex: number) {
  if (job.status === "completed") return "done";
  if (job.status === "failed") {
    if (currentIndex < 0) return index === 0 ? "failed" : "pending";
    if (index < currentIndex) return "done";
    if (index === currentIndex) return "failed";
    return "pending";
  }
  if (job.status === "queued") return "pending";
  if (currentIndex < 0) return index === 0 ? "active" : "pending";
  if (index < currentIndex) return "done";
  if (index === currentIndex) return "active";
  return "pending";
}

function JobDiagnostics({ job }: { job: Job }) {
  const warnings = job.warnings ?? [];
  const timings = job.timings ?? {};
  const items = [
    job.diarization_status ? `Diarization: ${job.diarization_status}` : "",
    job.asr_quality ? `ASR: ${qualityLabel(job.asr_quality)}` : "",
    job.raw_speaker_count ? `Acoustic: ${job.raw_speaker_count}` : "",
    job.speaker_count ? `Final labels: ${job.speaker_count}` : "",
    formatTiming(timings.total_job_seconds) ? `Total: ${formatTiming(timings.total_job_seconds)}` : "",
    formatTiming(timings.asr_seconds) ? `ASR: ${formatTiming(timings.asr_seconds)}` : "",
    formatTiming(timings.diarization_seconds) ? `Diarization: ${formatTiming(timings.diarization_seconds)}` : "",
  ].filter(Boolean);
  if (items.length === 0 && warnings.length === 0) return null;

  return (
    <div className="diagnostics">
      {items.map((item) => (
        <span key={item}>{item}</span>
      ))}
      {warnings.length > 0 && (
        <details className="warning-details">
          <summary>Warnings: {warnings.length}</summary>
          <div>
            {warnings.map((warning, index) => (
              <p key={`${index}-${warning}`}>{warning}</p>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function DownloadLink({
  jobId,
  format,
  label,
}: {
  jobId: string;
  format: "txt" | "raw-txt";
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

function formatDuration(value: number) {
  if (value < 60) return `${Math.max(1, Math.round(value))} сек`;
  return `${Math.floor(value / 60)} мин ${Math.round(value % 60)} сек`;
}

function estimateFromDuration(job: Job) {
  if (!job.source_duration_seconds) return null;
  const qualityFactors: Record<string, number> = { fast: 0.16, balanced: 0.29, accurate: 0.58, maximum: 0.58 };
  const profileFactors: Record<string, number> = { plain: 0, conservative: 0.01, speech: 0.02 };
  const audioProfile = job.audio_profile ?? autoAudioProfileForQuality(job.asr_quality ?? "balanced");
  return (
    job.source_duration_seconds
      * ((qualityFactors[job.asr_quality ?? "balanced"] ?? 0.55)
        + (profileFactors[audioProfile] ?? 0.04))
    + 15
  );
}

function fallbackOneHourEstimate(quality: string) {
  const qualityFactors: Record<string, number> = { fast: 0.16, balanced: 0.29, accurate: 0.58, maximum: 0.58 };
  const profileFactors: Record<string, number> = { plain: 0, conservative: 0.01, speech: 0.02 };
  const profile = autoAudioProfileForQuality(quality);
  return 3600 * ((qualityFactors[quality] ?? 0.55) + (profileFactors[profile] ?? 0.04)) + 15;
}

function autoAudioProfileForQuality(quality: string) {
  if (quality === "maximum") return "speech";
  return quality === "fast" ? "conservative" : "speech";
}

function apiQualityValue(quality: string) {
  return quality === "maximum" ? "accurate" : quality;
}

function qualityLabel(quality: string) {
  return quality === "accurate" ? "maximum" : quality;
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
  if (job.status === "processing") return job.progress_message ?? "Идет обработка аудио";
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
