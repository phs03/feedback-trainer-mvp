import { useState, useRef } from "react";

// --- API_BASE 설정 ---
// 기본값: 로컬 개발용 백엔드
let API_BASE = "http://127.0.0.1:8000";

// Vite 환경변수
const rawApiBase = import.meta.env.VITE_API_BASE_URL;

// 브라우저 환경에서 호스트를 보고 결정
if (typeof window !== "undefined") {
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    // 로컬 개발 환경 → 무조건 로컬 백엔드 사용
    API_BASE = "http://127.0.0.1:8000";
  } else if (rawApiBase && rawApiBase.trim()) {
    // 배포 환경 → .env에 지정한 백엔드 URL 사용
    API_BASE = rawApiBase.trim().replace(/\/+$/, "");
  }
}

console.log("[DEBUG] API_BASE =", API_BASE);

// --- 피드백 상황/스케일 옵션 ---
// value: scenario_code, scaleCode: scale_code
const SCENARIO_OPTIONS = [
  {
    value: "CLINICAL_OMP",
    label: "임상 진료 후 피드백 (One-Minute Preceptor)",
    scaleCode: "OMP_CORE_FIVE",
  },
];

const LANGUAGE_LABELS = {
  auto: "자동 (Auto)",
  ko: "한국어 (Korean)",
  en: "영어 (English)",
  ja: "일본어 (Japanese)",
  zh: "중국어 (Chinese)",
  es: "스페인어 (Spanish)",
  fr: "프랑스어 (French)",
  de: "독일어 (German)",
};

function normalizeLangCode(code) {
  if (!code) return null;
  const base = code.split("-")[0].toLowerCase();
  return base;
}

function renderDetectedLanguage(code) {
  if (!code) return "";
  const normalized = normalizeLangCode(code);
  const label = LANGUAGE_LABELS[normalized] || `코드: ${code}`;
  return `${label} (${code})`;
}

function App() {
  const [transcript, setTranscript] = useState(
    "먼저 너 생각은 어땠어? 나는 네가 ABC를 설명한 건 좋았다고 생각해. 아까 환자에게 문제를 설명했을 때, 네가 쉬운 말로 바꿔서 말한 점이 특히 좋았어. 정리하면 중요한 건 감별진단의 우선순위를 환자에게도 이해할 수 있게 설명하는 거야. 다음에는 처음 5분 안에 네 가설을 한 번 말해보고, 그걸 환자에게도 공유해보자."
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  // 🔹 선택된 시나리오/스케일 상태
const [scenarioCode, setScenarioCode] = useState("CLINICAL_OMP");
const [scaleCode, setScaleCode] = useState("OMP_CORE_FIVE");

  // 🔹 STT diarization 결과
  const [segments, setSegments] = useState([]);
  const [speakerMapping, setSpeakerMapping] = useState({
    SPEAKER_00: "지도전문의",
    SPEAKER_01: "전공의",
  });

  const [advancedMode, setAdvancedMode] = useState(false);

  // 🔹 언어 상태
  const [detectedLanguage, setDetectedLanguage] = useState(null);
  const [language, setLanguage] = useState("auto");

  // 🔹 녹음 관련 상태
  const [isRecording, setIsRecording] = useState(false);
  const [recordingStatus, setRecordingStatus] = useState("");
  const [audioUrl, setAudioUrl] = useState(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // 🔹 코칭 리포트 평가 상태 (도움 정도 1~5)
  const [coachEvalScore, setCoachEvalScore] = useState(null);
  const [coachEvalSending, setCoachEvalSending] = useState(false);
  const [coachEvalDone, setCoachEvalDone] = useState(false);
  const [coachEvalError, setCoachEvalError] = useState("");

  // 🔹 "어느 항목을 기록(저장)할지" 체크 상태
  //    키: strengths / improvements_top3 / script_next_time / micro_habit_10sec
  const [recordFlags, setRecordFlags] = useState([]);

  // 🔹 기록 저장 상태
  const [coachMemoSending, setCoachMemoSending] = useState(false);
  const [coachMemoDone, setCoachMemoDone] = useState(false);
  const [coachMemoError, setCoachMemoError] = useState("");

  // 🔹 시나리오 선택 변경
  function handleScenarioChange(e) {
    const value = e.target.value;
    setScenarioCode(value);
    const found = SCENARIO_OPTIONS.find((opt) => opt.value === value);
    if (found) {
      setScaleCode(found.scaleCode);
    }
  }

  // 🔹 "기록" 체크 토글 함수
  function toggleRecordFlag(flag) {
    setRecordFlags((prev) =>
      prev.includes(flag) ? prev.filter((f) => f !== flag) : [...prev, flag]
    );
  }

  // 🔹 분석 API 호출
  async function handleAnalyze(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    // 새 분석 시작 시 평가/기록 관련 상태 초기화
    setCoachEvalScore(null);
    setCoachEvalDone(false);
    setCoachEvalError("");
    setRecordFlags([]);
    setCoachMemoSending(false);
    setCoachMemoDone(false);
    setCoachMemoError("");

    try {
      const payload = {
        encounter_id: "UI-TEST-001", // TODO: 나중에 실제 encounter_id로 변경
        supervisor_id: "S-UI-001",
        trainee_id: "T-UI-001",
        audio_ref: null,
        transcript: transcript,
        trainee_level: "PGY-2",
        language: language,
        scale_code: scaleCode,
        scenario_code: scenarioCode,
        context: {
          case: "ER teaching feedback",
          language: language,
          note: "ui test",
        },
        segments: segments,
        speaker_mode: advancedMode ? "manual" : "auto",
        speaker_mapping: advancedMode ? speakerMapping : {},
      };

      const url = `${API_BASE}/feedback`;
      console.log("[DEBUG] 분석 요청 URL:", url, payload);

      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
        cache: "no-store",
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`서버 오류: ${res.status} - ${text}`);
      }

      const data = await res.json();
      console.log("[DEBUG] 분석 응답:", data);
      setResult(data);
    } catch (err) {
      console.error(err);
      setError(err.message || "알 수 없는 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  }

  // 🔹 녹음 시작
  async function handleStartRecording() {
    setError("");

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError("이 브라우저에서는 녹음 기능을 지원하지 않습니다.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);

      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstart = () => {
        setIsRecording(true);
        setRecordingStatus("🎙 녹음 중입니다... (Recording)");
        setAudioUrl(null);
        setSegments([]);
        setDetectedLanguage(null);
      };

      mediaRecorder.onstop = async () => {
        setIsRecording(false);
        setRecordingStatus(
          "🎧 녹음 완료! 재생 또는 텍스트 변환을 진행하세요. (Recording finished)"
        );

        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });

        const url = URL.createObjectURL(audioBlob);
        setAudioUrl(url);

        console.log("녹음된 Blob:", audioBlob);
      };

      mediaRecorder.start();
    } catch (err) {
      console.error(err);
      setError("마이크 사용 권한을 허용했는지 확인해주세요.");
    }
  }

  // 🔹 녹음 종료
  function handleStopRecording() {
    const mediaRecorder = mediaRecorderRef.current;
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
  }

  // 🔹 녹음 재생
  function handlePlayRecording() {
    if (!audioUrl) {
      setRecordingStatus(
        "⚠ 아직 재생할 녹음이 없습니다. (No recording to play)"
      );
      return;
    }
    const audio = new Audio(audioUrl);
    audio.play().catch((err) => {
      console.error("재생 실패:", err);
      setRecordingStatus("⚠ 재생 중 오류가 발생했습니다. (Play error)");
    });
  }

  // 🔹 STT 호출 (녹음된 Blob → STT + Speaker Diarization)
  async function handleTranscribeRecording() {
    setError("");
    setRecordingStatus("🧠 텍스트 변환 중... (Converting to text)");

    try {
      if (!audioChunksRef.current.length) {
        setRecordingStatus(
          "⚠ 변환할 녹음 데이터가 없습니다. (No audio to convert)"
        );
        return;
      }

      const audioBlob = new Blob(audioChunksRef.current, {
        type: "audio/webm",
      });

      const formData = new FormData();
      formData.append("file", audioBlob, "recording.webm");

      const url = `${API_BASE}/api/stt`;
      console.log("[DEBUG] STT 요청 URL:", url);

      const res = await fetch(url, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        console.error("[STT ERROR RES BODY]", text);
        throw new Error(`STT 요청 실패: ${res.status} - ${text}`);
      }

      const data = await res.json();
      console.log("STT 응답(raw):", data);

      if (!data) {
        setRecordingStatus(
          "❌ STT 응답이 비어 있습니다(null). (Empty STT response)"
        );
        setError(
          "STT 응답이 null 입니다. /api/stt 백엔드 응답 구조를 한 번 확인해 주세요."
        );
        return;
      }

      const sttText = data.transcript || data.text || "";
      const sttSegments = data.segments || [];
      const sttLang = data.language || null;

      if (!sttText && sttSegments.length === 0) {
        setRecordingStatus(
          "⚠ STT 응답에 텍스트/segments가 없습니다. (No text/segments in STT response)"
        );
      }

      if (sttText) {
        setTranscript(sttText);
      }
      setSegments(sttSegments);

      if (sttLang) {
        setDetectedLanguage(sttLang);

        const normalized = normalizeLangCode(sttLang);
        if (normalized && LANGUAGE_LABELS[normalized]) {
          setLanguage(normalized);
        } else {
          setLanguage("auto");
        }
      }

      if (sttText || sttSegments.length > 0) {
        setRecordingStatus(
          "✅ 텍스트 변환 완료! 아래 입력창과 화자별 영역에서 내용을 확인하세요. (Conversion done)"
        );
      }
    } catch (err) {
      console.error(err);
      setRecordingStatus(
        "❌ 음성 → 텍스트 변환 실패 (STT failed, see error above)"
      );
      setError(err.message || "STT 중 오류가 발생했습니다.");
    }
  }

  // 🔹 Speaker label을 사람 역할로 보여주기
  function renderSpeakerLabel(speaker) {
  // Advanced Mode에서는 사용자가 직접 지정한 역할 사용
  // 기본 모드에서는 AI가 추론한 역할 사용
    const activeMapping = advancedMode
      ? speakerMapping
      : aiSpeakerMapping;

    const role = activeMapping[speaker] || speaker;

    if (role === "지도전문의") {
      return `지도전문의 (Supervisor) · ${speaker}`;
    }

    if (role === "전공의") {
      return `전공의 (Resident) · ${speaker}`;
    }

    if (role === "기타") {
      return `기타 (Other) · ${speaker}`;
    }

    return speaker;
  }

  function handleSpeakerSelectChange(speakerKey, value) {
    setSpeakerMapping((prev) => ({
      ...prev,
      [speakerKey]: value,
    }));
  }

  // 🔹 segments에 포함된 speaker 목록 추출
  const uniqueSpeakers = Array.from(
    new Set((segments || []).map((s) => s.speaker))
  );

  // 🔹 index 정보가 붙은 segments
  const indexedSegments = (segments || []).map((seg, idx) => ({
    ...seg,
    _idx: idx,
  }));

  // 🔹 역할별 segment 분리
  const traineeSegments = indexedSegments.filter(
    (seg) => speakerMapping[seg.speaker] === "전공의"
  );
  const supervisorSegments = indexedSegments.filter(
    (seg) => speakerMapping[seg.speaker] === "지도전문의"
  );

  // 🔹 특정 segment index에 해당하는 OSAD/OMP 근거 태그들 구하기
  function getOsadTagsForSegment(segIndex) {
    if (!result || !result.evidence || !result.evidence.osad) return [];
    const ev = result.evidence.osad;
    const tags = [];
    for (const [dim, indices] of Object.entries(ev)) {
      if (Array.isArray(indices) && indices.includes(segIndex)) {
        tags.push(dim);
      }
    }
    return tags;
  }

const speakerAnalysis = result?.speaker_analysis || null;
const aiSpeakerMapping = speakerAnalysis?.mapping || {};

const speakerConfidence =
  speakerAnalysis?.confidence !== undefined &&
  speakerAnalysis?.confidence !== null &&
  !Number.isNaN(Number(speakerAnalysis.confidence))
    ? Number(speakerAnalysis.confidence)
    : null;

const speakerConfidenceLabel =
  speakerAnalysis?.mode === "manual"
    ? "사용자 직접 지정"
    : speakerAnalysis?.confidence_label === "high"
      ? "높음"
      : speakerAnalysis?.confidence_label === "medium"
        ? "보통"
        : speakerAnalysis?.confidence_label === "low"
          ? "낮음"
          : "확인 불가";


  const osadEvidence = result?.evidence?.osad || {};

  // 🔹 점수/퍼센트 계산 (백엔드에서 준 scale 사용)
  const osadTotal =
    result && result.osad && typeof result.osad.total === "number"
      ? result.osad.total
      : null;

  const osadScale =
    result && result.osad && typeof result.osad.scale === "number"
      ? result.osad.scale
      : 45;

  const osadPercent =
    osadTotal !== null && osadScale > 0
      ? Math.round((osadTotal / osadScale) * 1000) / 10
      : null;

  const osadPercentClamped =
    typeof osadPercent === "number"
      ? Math.min(100, Math.max(0, osadPercent))
      : 0;

  // 🔹 코칭 리포트 평가 전송 함수 (도움 정도 1~5)
  async function handleCoachEval(score) {
    if (!result) return;
    if (coachEvalSending || coachEvalDone) return;

    setCoachEvalError("");
    setCoachEvalSending(true);
    setCoachEvalScore(score);

    try {
      const payload = {
        encounter_id: "UI-TEST-001",
        scenario_code: scenarioCode,
        scale_code: scaleCode,
        model_version: "gpt-4o-mini-omp-v1",
        helpful_score: score,
        helpful_flags: recordFlags.length ? recordFlags : null,
        comment: null,
      };

      const url = `${API_BASE}/feedback/coach-eval`;
      console.log("[DEBUG] coach-eval 요청 URL:", url, payload);

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`coach-eval 서버 오류: ${res.status} - ${text}`);
      }

      const data = await res.json();
      console.log("[DEBUG] coach-eval 응답:", data);
      setCoachEvalDone(true);
    } catch (err) {
      console.error(err);
      setCoachEvalError(
        err.message || "코칭 리포트 평가 전송 중 오류가 발생했습니다."
      );
    } finally {
      setCoachEvalSending(false);
    }
  }

  // 🔹 "기록"으로 체크된 섹션들을 실제로 저장하는 함수
  async function handleSaveCoachMemo() {
    if (!result) return;

    setCoachMemoError("");
    setCoachMemoDone(false);

    const selected = {};

    if (recordFlags.includes("strengths")) {
      const lines = Array.isArray(result.coach.strengths)
        ? result.coach.strengths
        : [];
      if (lines.length > 0) {
        selected.strengths = lines.join("\n");
      }
    }

    if (recordFlags.includes("improvements_top3")) {
      const lines = Array.isArray(result.coach.improvements_top3)
        ? result.coach.improvements_top3
        : [];
      if (lines.length > 0) {
        selected.improvements_top3 = lines.join("\n");
      }
    }

    if (recordFlags.includes("script_next_time")) {
      if (result.coach.script_next_time) {
        selected.script_next_time = result.coach.script_next_time;
      }
    }

    if (recordFlags.includes("micro_habit_10sec")) {
      if (result.coach.micro_habit_10sec) {
        selected.micro_habit_10sec = result.coach.micro_habit_10sec;
      }
    }

    if (Object.keys(selected).length === 0) {
      setCoachMemoError(
        "기록할 항목을 최소 1개 이상 선택해 주세요. (각 제목 옆 '기록' 체크)"
      );
      return;
    }

    setCoachMemoSending(true);

    try {
      const payload = {
        encounter_id: "UI-TEST-001",
        supervisor_id: "S-UI-001",
        trainee_id: "T-UI-001",
        scenario_code: scenarioCode,
        scale_code: scaleCode,
        model_version: "gpt-4o-mini-omp-v1",
        saved_sections: selected,
        note: null,
      };

      const url = `${API_BASE}/feedback/coach-memo`;
      console.log("[DEBUG] coach-memo 요청 URL:", url, payload);

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`coach-memo 서버 오류: ${res.status} - ${text}`);
      }

      const data = await res.json();
      console.log("[DEBUG] coach-memo 응답:", data);
      setCoachMemoDone(true);
    } catch (err) {
      console.error(err);
      setCoachMemoError(
        err.message || "코칭 리포트 기록 저장 중 오류가 발생했습니다."
      );
    } finally {
      setCoachMemoSending(false);
    }
  }
  
  return (
  <div className="app-shell">
    <div className="app-container">
<h1 className="h1">
  One-Minute Preceptor 피드백 코칭
</h1>
<p className="p-muted">
  지도전문의와 전공의의 짧은 임상 피드백 대화를 분석하여
  One-Minute Preceptor의 5개 microskill을 평가하고,
  다음 피드백에 활용할 수 있는 구체적인 코칭을 제공합니다.
</p>

      {/* 🔹 시나리오 / 스케일 선택 */}
      <section className="card purple">
        <div className="row">
          <span style={{ fontWeight: 600 }}>피드백 상황 선택:</span>
          <select className="select" value={scenarioCode} onChange={handleScenarioChange}>
            {SCENARIO_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
<span className="muted" style={{ fontSize: 13 }}>
  임상 현장의 짧은 지도전문의-전공의 피드백 분석
</span>
        </div>

        <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
          API에 전송되는 scale_code: <code className="code">{scaleCode}</code>, scenario_code:{" "}
          <code className="code">{scenarioCode}</code>
        </div>
      </section>

      {/* 🔹 1. 음성 녹음 영역 */}
      <section className="card">
        <h2 className="h2">1. 음성 녹음하기 (Record audio)</h2>
        <p className="small" style={{ marginBottom: 10 }}>
          지도전문의-전공의 피드백 장면을 이 브라우저에서 바로 녹음합니다.
          (녹음 종료 후 재생 및 STT + 화자 구분으로 텍스트로 변환할 수 있습니다.)
        </p>

        <div className="row" style={{ marginBottom: 8 }}>
          <button type="button" onClick={handleStartRecording} disabled={isRecording} className="btn ghost">
            🎙 녹음 시작 (Start recording)
          </button>
          <button type="button" onClick={handleStopRecording} disabled={!isRecording} className="btn ghost">
            ⏹ 녹음 종료 (Stop)
          </button>
          <button type="button" onClick={handlePlayRecording} disabled={!audioUrl} className="btn ghost">
            ▶ 녹음 재생 (Play)
          </button>
          <button
            type="button"
            onClick={handleTranscribeRecording}
            disabled={!audioChunksRef.current.length}
            className="btn ghost"
          >
            ✨ 텍스트 변환 (Convert to text with speakers)
          </button>
        </div>

        {recordingStatus && <p className="status">{recordingStatus}</p>}

        {/* 🔹 STT에서 감지한 언어 + 코칭 언어 선택 */}
        <div className="card soft" style={{ marginTop: 12 }}>
          {detectedLanguage && (
            <div style={{ marginBottom: 8, fontSize: 13 }}>
              <strong>자동 감지된 언어 (Detected language):</strong>{" "}
              {renderDetectedLanguage(detectedLanguage)}
            </div>
          )}

          <div className="row" style={{ fontSize: 13 }}>
            <span>
              <strong>사용 언어 (Language for coaching):</strong>
            </span>
            <select className="select" value={language} onChange={(e) => setLanguage(e.target.value)}>
              {Object.entries(LANGUAGE_LABELS).map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
            <span className="muted">
              (자동: 지도전문의 발언 언어를 추론하여 사용, 불분명하면 한국어)
            </span>
          </div>
        </div>
      </section>

      {/* 🔹 Advanced Mode 설정: 녹음/STT 전에도 항상 표시 */}
      <section className="card soft">
        <div className="advanced-mode-box">
          <label className="row" style={{ gap: 8, fontWeight: 600 }}>
            <input
              type="checkbox"
              checked={advancedMode}
              onChange={(e) => setAdvancedMode(e.target.checked)}
            />
            <span>Advanced Mode: 화자 역할 직접 지정</span>
          </label>

          <p className="hint-text" style={{ marginTop: 8, marginBottom: 0 }}>
            {advancedMode
              ? "고급 모드에서는 각 화자의 역할을 직접 지정합니다."
              : "기본 모드에서는 AI가 지도전문의와 전공의 역할을 자동으로 추론합니다."}
          </p>
        </div>
      </section>

      {/* 🔹 1-2. 화자별 transcript 미리보기 */}
      {segments && segments.length > 0 && (
        <section className="card soft">
          <h2 className="h2">1-2. 화자별 transcript (Speaker diarization)</h2>

          {/* 화자 역할 매핑: Advanced Mode에서만 표시 */}
          {advancedMode && uniqueSpeakers.length > 0 && (
            <div
              className="row"
              style={{ marginBottom: 12, fontSize: 13, gap: 12 }}
            >
              {uniqueSpeakers.map((spk) => (
                <div key={spk} className="row" style={{ gap: 8 }}>
                  <span>{spk} → </span>
                  <select
                    className="select"
                    value={speakerMapping[spk] || spk}
                    onChange={(e) =>
                      handleSpeakerSelectChange(spk, e.target.value)
                    }
                    style={{ fontSize: 13 }}
                  >
                    <option value={spk}>{spk}</option>
                    <option value="지도전문의">
                      지도전문의 (Supervisor)
                    </option>
                    <option value="전공의">전공의 (Resident)</option>
                    <option value="기타">기타 (Other)</option>
                  </select>
                </div>
              ))}
            </div>
          )}

          {/* segment 리스트 */}
          <div className="scroll">
            {indexedSegments.map((seg) => {
              const idx = seg._idx;
              const tags = getOsadTagsForSegment(idx);

              return (
                <div key={idx} className="seg">
                  <div className="seg-head">
                    <span style={{ fontWeight: 600 }}>
                        {renderSpeakerLabel(seg.speaker)}
                    </span>
                    <span>
                      {seg.start?.toFixed
                        ? seg.start.toFixed(1)
                        : seg.start}{" "}
                      s ~{" "}
                      {seg.end?.toFixed ? seg.end.toFixed(1) : seg.end} s
                    </span>
                  </div>

                  <div style={{ marginBottom: tags.length ? 6 : 0 }}>
                    {seg.text}
                  </div>

                  {tags.length > 0 && (
                    <div className="tags">
                      {tags.map((t) => (
                        <span key={t} className="tag">
                          OMP: {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 🔹 1-3. 역할별 발언 분리: Advanced Mode에서만 표시 */}
      {advancedMode && segments && segments.length > 0 && (
        <section className="card white" style={{ marginBottom: 24 }}>
          <h2 className="h2">1-3. 역할별 발언 분리 (By role)</h2>
          <p className="small" style={{ marginBottom: 10 }}>
            좌측에는 전공의 발언, 우측에는 지도전문의 발언만 시간
            순서대로 모아서 보여줍니다. (Left: Resident, Right:
            Supervisor)
          </p>

          <div className="two-col">
            {/* 전공의 발언 */}
            <div className="col">
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  marginBottom: 8,
                }}
              >
                전공의 발언 (Resident)
              </div>

              {traineeSegments.length === 0 ? (
                <p
                  className="muted"
                  style={{ fontSize: 13, fontStyle: "italic" }}
                >
                  전공의로 분류된 발언이 아직 없습니다. (No resident
                  utterance yet)
                </p>
              ) : (
                <div className="scroll" style={{ maxHeight: 200 }}>
                  {traineeSegments.map((seg) => {
                    const idx = seg._idx;
                    const tags = getOsadTagsForSegment(idx);

                    return (
                      <div key={idx} className="seg">
                        <div
                          className="muted"
                          style={{ fontSize: 12, marginBottom: 4 }}
                        >
                          {seg.start?.toFixed
                            ? seg.start.toFixed(1)
                            : seg.start}{" "}
                          s ~{" "}
                          {seg.end?.toFixed
                            ? seg.end.toFixed(1)
                            : seg.end}{" "}
                          s
                        </div>

                        <div style={{ marginBottom: tags.length ? 6 : 0 }}>
                          {seg.text}
                        </div>

                        {tags.length > 0 && (
                          <div className="tags">
                            {tags.map((t) => (
                              <span key={t} className="tag">
                                OMP: {t}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 지도전문의 발언 */}
            <div className="col">
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  marginBottom: 8,
                }}
              >
                지도전문의 발언 (Supervisor)
              </div>

              {supervisorSegments.length === 0 ? (
                <p
                  className="muted"
                  style={{ fontSize: 13, fontStyle: "italic" }}
                >
                  지도전문의로 분류된 발언이 아직 없습니다. (No
                  supervisor utterance yet)
                </p>
              ) : (
                <div className="scroll" style={{ maxHeight: 200 }}>
                  {supervisorSegments.map((seg) => {
                    const idx = seg._idx;
                    const tags = getOsadTagsForSegment(idx);

                    return (
                      <div key={idx} className="seg">
                        <div
                          className="muted"
                          style={{ fontSize: 12, marginBottom: 4 }}
                        >
                          {seg.start?.toFixed
                            ? seg.start.toFixed(1)
                            : seg.start}{" "}
                          s ~{" "}
                          {seg.end?.toFixed
                            ? seg.end.toFixed(1)
                            : seg.end}{" "}
                          s
                        </div>

                        <div style={{ marginBottom: tags.length ? 6 : 0 }}>
                          {seg.text}
                        </div>

                        {tags.length > 0 && (
                          <div className="tags">
                            {tags.map((t) => (
                              <span key={t} className="tag">
                                OMP: {t}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* 🔹 2. 텍스트 입력 + 분석 */}
      <form onSubmit={handleAnalyze}>
        <label htmlFor="transcript" className="label">
          2. 피드백 대화 transcript
        </label>
        <textarea
          id="transcript"
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          rows={8}
          className={`textarea ${error ? "error" : ""}`}
        />

        <div className="row" style={{ marginTop: 12 }}>
          <button
            type="submit"
            disabled={loading || !transcript.trim()}
            className={`btn primary full`}
          >
            {loading ? "분석 중... (Analyzing)" : "피드백 분석하기 (Analyze feedback)"}
          </button>
        </div>
      </form>

      {error && <div className="err">오류: {error}</div>}

      {result && (
        <div className="results">

{/* 🔹 AI 화자 역할 추론 결과 */}
{speakerAnalysis && (
  <section className="card soft">
<div
  className="row"
  style={{
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  }}
>
  <h2 className="h2" style={{ margin: 0 }}>
    화자 역할 분석 (Speaker role analysis)
  </h2>

  <span
    style={{
      display: "inline-block",
      padding: "5px 10px",
      borderRadius: 999,
      fontSize: 13,
      fontWeight: 700,
      background:
        speakerAnalysis.mode === "manual"
          ? "#ecfdf5"
          : speakerAnalysis.confidence_label === "high"
            ? "#ecfdf5"
            : speakerAnalysis.confidence_label === "medium"
              ? "#fffbeb"
              : "#fff7ed",
      color:
        speakerAnalysis.mode === "manual"
          ? "#047857"
          : speakerAnalysis.confidence_label === "high"
            ? "#047857"
            : speakerAnalysis.confidence_label === "medium"
              ? "#92400e"
              : "#9a3412",
    }}
  >
    신뢰도: {speakerConfidenceLabel}
    {speakerAnalysis.mode !== "manual" &&
      speakerConfidence !== null &&
      ` (${Math.round(speakerConfidence * 100)}%)`}
  </span>
</div>

    <div
      style={{
        display: "grid",
        gridTemplateColumns:
          "repeat(auto-fit, minmax(220px, 1fr))",
        gap: 10,
        marginBottom: 12,
      }}
    >
      {Object.entries(aiSpeakerMapping).map(
        ([speaker, role]) => (
          <div
            key={speaker}
            style={{
              padding: 10,
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              background: "#ffffff",
            }}
          >
            <div
              className="muted"
              style={{ fontSize: 12, marginBottom: 4 }}
            >
              {speaker}
            </div>

            <div style={{ fontWeight: 700 }}>
              {role === "지도전문의"
                ? "지도전문의 (Supervisor)"
                : role === "전공의"
                  ? "전공의 (Resident)"
                  : "기타 (Other)"}
            </div>
          </div>
        )
      )}
    </div>

    <div style={{ fontSize: 13 }}>
      <strong>분석 방식:</strong>{" "}
      {speakerAnalysis.mode === "manual"
        ? "Advanced Mode에서 사용자가 직접 지정"
        : "AI 자동 역할 추론"}
    </div>

    {speakerAnalysis.reason && (
      <p
        className="small"
        style={{
          marginTop: 8,
          marginBottom: 0,
        }}
      >
        {speakerAnalysis.reason}
      </p>
    )}

    {speakerAnalysis.uncertain && (
      <div
        style={{
          marginTop: 10,
          padding: 10,
          borderRadius: 8,
          background: "#fff7ed",
          color: "#9a3412",
          fontSize: 13,
        }}
      >
        ⚠ 화자 역할 추론이 불확실합니다. 필요한 경우
        Advanced Mode에서 역할을 직접 지정한 후 다시
        분석하세요.
      </div>
    )}
  </section>
)}


          {/* 점수 요약 */}
          <section className="card">
            <h2 className="h2">점수 요약 (Scores)</h2>

            <p className="small" style={{ marginBottom: 10 }}>
              총점 (Total score): <strong>{osadTotal !== null ? osadTotal : "-"}</strong>
              점 / <strong>{osadScale}</strong>점{" "}
              {typeof osadPercent === "number" && (
                <>
                  (<strong>{osadPercent}%</strong>)
                </>
              )}
            </p>

            {typeof osadPercent === "number" && (
              <div className="progress" style={{ marginBottom: 12 }}>
                <div style={{ width: osadPercentClamped + "%" }} />
              </div>
            )}

            {/* 차원별 점수 */}
            {result.osad && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                  gap: "6px 12px",
                  fontSize: 13,
                }}
              >
                {Object.entries(result.osad)
                  .filter(([key]) => !["total", "scale", "percent"].includes(key))
                  .map(([key, val]) => (
                    <div
                      key={key}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        borderBottom: "1px dashed #e5e7eb",
                        paddingBottom: 4,
                        gap: 10,
                      }}
                    >
                      <span style={{ color: "#374151" }}>{key}</span>
                      <span style={{ fontWeight: 700 }}>{String(val)}</span>
                    </div>
                  ))}
              </div>
            )}

            {Object.keys(osadEvidence).length > 0 && (
              <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
* OMP 태그가 붙은 발언은 해당 microskill 평가의 근거로 사용되었습니다.              </p>
            )}
          </section>

          {/* 구조 분석 */}
          {result.structure && (
            <section className="card">
              <h2 className="h2">구조 분석 (Structure: Opening / Core / Closing)</h2>
              <ul style={{ listStyle: "none", paddingLeft: 0, fontSize: 14, margin: 0 }}>
                <li>{result.structure.has_opening ? "✅" : "❌"} Opening (전공의 의견/생각을 묻는 시작)</li>
                <li>{result.structure.has_core ? "✅" : "❌"} Core (관찰·이유·결과 등 핵심 내용)</li>
                <li>{result.structure.has_closing ? "✅" : "❌"} Closing (요약·다음 단계 제시)</li>
              </ul>
            </section>
          )}

          {/* 코칭 리포트 */}
          {result.coach && (
            <section className="card">
              <h2 className="h2">코칭 리포트 (Coaching report)</h2>

              {/* 강점 */}
              <div style={{ marginBottom: 14 }}>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                  <h3 className="h3">강점 (Strengths)</h3>
                  <label className="row" style={{ gap: 6, fontSize: 12, color: "#374151" }}>
                    <input
                      type="checkbox"
                      checked={recordFlags.includes("strengths")}
                      onChange={() => toggleRecordFlag("strengths")}
                    />
                    <span>기록</span>
                  </label>
                </div>
                <ul style={{ paddingLeft: 18, fontSize: 14, marginTop: 0 }}>
                  {Array.isArray(result.coach.strengths) &&
                    result.coach.strengths.map((s, idx) => <li key={idx}>{s}</li>)}
                </ul>
              </div>

              {/* 개선 상위 3가지 */}
              <div style={{ marginBottom: 14 }}>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                  <h3 className="h3">개선이 필요한 상위 3가지 (Top 3 improvements)</h3>
                  <label className="row" style={{ gap: 6, fontSize: 12, color: "#374151" }}>
                    <input
                      type="checkbox"
                      checked={recordFlags.includes("improvements_top3")}
                      onChange={() => toggleRecordFlag("improvements_top3")}
                    />
                    <span>기록</span>
                  </label>
                </div>
                <ul style={{ paddingLeft: 18, fontSize: 14, marginTop: 0 }}>
                  {Array.isArray(result.coach.improvements_top3) &&
                    result.coach.improvements_top3.map((s, idx) => <li key={idx}>{s}</li>)}
                </ul>
              </div>

              {/* Script next time */}
              <div style={{ marginBottom: 12 }}>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                  <h3 className="h3">다음에 이렇게 말해보세요 (Script next time)</h3>
                  <label className="row" style={{ gap: 6, fontSize: 12, color: "#374151" }}>
                    <input
                      type="checkbox"
                      checked={recordFlags.includes("script_next_time")}
                      onChange={() => toggleRecordFlag("script_next_time")}
                    />
                    <span>기록</span>
                  </label>
                </div>
                <p style={{ fontSize: 14, whiteSpace: "pre-wrap", margin: 0 }}>{result.coach.script_next_time}</p>
              </div>

              {/* 10초 미세 습관 */}
              <div style={{ marginBottom: 6 }}>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                  <h3 className="h3">10초짜리 미세 습관 (10-second micro habit)</h3>
                  <label className="row" style={{ gap: 6, fontSize: 12, color: "#374151" }}>
                    <input
                      type="checkbox"
                      checked={recordFlags.includes("micro_habit_10sec")}
                      onChange={() => toggleRecordFlag("micro_habit_10sec")}
                    />
                    <span>기록</span>
                  </label>
                </div>
                <p style={{ fontSize: 14, whiteSpace: "pre-wrap", margin: 0 }}>{result.coach.micro_habit_10sec}</p>
              </div>

              {/* ✅ 전체 도움 정도 평가 + 기록 저장 */}
              <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid #e5e7eb", fontSize: 13 }}>
                <div style={{ marginBottom: 8 }}>이 코칭 리포트는 전체적으로 얼마나 도움이 되었나요?</div>

                <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                  {[1, 2, 3, 4, 5].map((score) => {
                    const isSelected = coachEvalScore === score;
                    return (
                      <button
                        key={score}
                        type="button"
                        onClick={() => handleCoachEval(score)}
                        disabled={coachEvalSending || coachEvalDone}
                        className="btn pill"
                        style={{
                          borderColor: isSelected ? "var(--brand)" : "#d1d5db",
                          background: isSelected ? "var(--brand)" : "#fff",
                          color: isSelected ? "#fff" : "#111827",
                        }}
                      >
                        {score}
                      </button>
                    );
                  })}
                </div>

                <div className="muted" style={{ fontSize: 12 }}>
                  1 = 전혀 도움이 되지 않았다, 5 = 매우 도움이 되었다
                </div>

                {coachEvalSending && <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>평가를 전송하는 중입니다...</div>}
                {coachEvalDone && <div style={{ marginTop: 8, fontSize: 12, color: "#059669" }}>감사합니다! 코칭 리포트 품질을 개선하는 데 활용하겠습니다.</div>}
                {coachEvalError && <div style={{ marginTop: 8, fontSize: 12, color: "#b91c1c" }}>{coachEvalError}</div>}

                <div className="row" style={{ marginTop: 12, gap: 8 }}>
                  <button
                    type="button"
                    onClick={handleSaveCoachMemo}
                    disabled={coachMemoSending}
                    className="btn"
                    style={{
                      borderColor: "#10b981",
                      background: coachMemoSending ? "#a7f3d0" : "#10b981",
                      color: "#fff",
                    }}
                  >
                    코칭 리포트 기록 저장하기
                  </button>
                  <span className="muted" style={{ fontSize: 12 }}>
                    각 섹션 제목 옆의 {"'기록'"} 체크가 된 항목들이 저장됩니다.
                  </span>
                </div>

                {coachMemoSending && <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>기록을 저장하는 중입니다...</div>}
                {coachMemoDone && <div style={{ marginTop: 8, fontSize: 12, color: "#059669" }}>기록이 저장되었습니다. (나중에 마이페이지/히스토리 화면에서 열람 가능하게 확장할 수 있습니다.)</div>}
                {coachMemoError && <div style={{ marginTop: 8, fontSize: 12, color: "#b91c1c" }}>{coachMemoError}</div>}
              </div>
            </section>
          )}

          {/* 디버깅용 Raw JSON */}
          <section className="mono-panel">
            <h2 style={{ fontSize: 15, fontWeight: 700, margin: "0 0 8px" }}>Raw JSON (디버깅용 / for debugging)</h2>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </section>
        </div>
      )}
    </div>
  </div>
  );

}

export default App;
