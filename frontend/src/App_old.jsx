import { useState, useRef } from "react";

// --- API_BASE 설정 ---
// 기본값: 로컬 개발용 백엔드
let API_BASE = "http://127.0.0.1:8000";

// Vite 환경변수
const rawApiBase = import.meta.env.VITE_API_BASE_URL;

if (typeof window !== "undefined") {
  const host = window.location.hostname;
  const isLocalHost = host === "localhost" || host === "127.0.0.1";

  if (isLocalHost) {
    // 로컬 개발 환경 → 항상 로컬 백엔드
    API_BASE = "http://127.0.0.1:8000";
  } else if (rawApiBase && rawApiBase.trim()) {
    // 배포 환경 + env가 설정된 경우
    API_BASE = rawApiBase.trim().replace(/\/+$/, "");
  } else {
    // 배포 환경인데 env가 비어 있으면, Render 백엔드로 강제 fallback
    API_BASE = "https://feedback-trainer-mvp.onrender.com";
  }
}

console.log("[DEBUG] API_BASE =", API_BASE);


function App() {
  const [transcript, setTranscript] = useState(
    "먼저 너 생각은 어땠어? 나는 네가 ABC를 설명한 건 좋았다고 생각해. 아까 환자에게 문제를 설명했을 때, 네가 쉬운 말로 바꿔서 말한 점이 특히 좋았어. 정리하면 중요한 건 감별진단의 우선순위를 환자에게도 이해할 수 있게 설명하는 거야. 다음에는 처음 5분 안에 네 가설을 한 번 말해보고, 그걸 환자에게도 공유해보자."
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  // 🔹 STT diarization 결과
  const [segments, setSegments] = useState([]);
  const [speakerMapping, setSpeakerMapping] = useState({
    SPEAKER_00: "지도전문의",
    SPEAKER_01: "전공의",
  });

  // 🔹 녹음 관련 상태
  const [isRecording, setIsRecording] = useState(false);
  const [recordingStatus, setRecordingStatus] = useState("");
  const [audioUrl, setAudioUrl] = useState(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // 🔹 OSAD 분석 API 호출
  async function handleAnalyze(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const payload = {
        encounter_id: "UI-TEST-001",
        supervisor_id: "S-UI-001",
        trainee_id: "T-UI-001",
        audio_ref: null,
        transcript: transcript,
        trainee_level: "PGY-2",
        language: "ko",
        context: {
          case: "ER teaching feedback",
          language: "ko",
          note: "ui test",
        },
        // 🔹 화자 정보까지 같이 보냄 (나중에 백엔드 evidence에 사용)
        segments: segments,
        speaker_mapping: speakerMapping, // 🔹 SPEAKER_00 → "지도전문의"/"전공의" 정보 전달
      };

      const url = `${API_BASE}/feedback`;
      console.log("[DEBUG] OSAD 요청 URL:", url);

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
      console.log("[DEBUG] OSAD 응답:", data);
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
        setRecordingStatus("🎙 녹음 중입니다...");
        setAudioUrl(null); // 이전 녹음 URL 초기화
        setSegments([]); // 이전 diarization 결과 초기화
      };

      mediaRecorder.onstop = async () => {
        setIsRecording(false);
        setRecordingStatus("🎧 녹음 완료! 재생 또는 텍스트 변환을 진행하세요.");

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
      setRecordingStatus("⚠ 아직 재생할 녹음이 없습니다.");
      return;
    }
    const audio = new Audio(audioUrl);
    audio.play().catch((err) => {
      console.error("재생 실패:", err);
      setRecordingStatus("⚠ 재생 중 오류가 발생했습니다.");
    });
  }

  // 🔹 STT 호출 (녹음된 Blob → STT + Speaker Diarization)
  async function handleTranscribeRecording() {
    setError("");
    setRecordingStatus("🧠 텍스트 변환 중...");

    try {
      if (!audioChunksRef.current.length) {
        setRecordingStatus("⚠ 변환할 녹음 데이터가 없습니다.");
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
        setRecordingStatus("❌ STT 응답이 비어 있습니다(null).");
        setError(
          "STT 응답이 null 입니다. /api/stt 백엔드 응답 구조를 한 번 확인해 주세요."
        );
        return;
      }

      const sttText = data.transcript || data.text || "";
      const sttSegments = data.segments || [];

      if (!sttText && sttSegments.length === 0) {
        setRecordingStatus("⚠ STT 응답에 텍스트/segments가 없습니다.");
      }

      if (sttText) {
        setTranscript(sttText);
      }
      setSegments(sttSegments);

      if (sttText || sttSegments.length > 0) {
        setRecordingStatus(
          "✅ 텍스트 변환 완료! 아래 입력창과 화자별 영역에서 내용을 확인하세요."
        );
      }
    } catch (err) {
      console.error(err);
      setRecordingStatus("❌ 음성 → 텍스트 변환 실패");
      setError(err.message || "STT 중 오류가 발생했습니다.");
    }
  }

  // 🔹 Speaker label을 사람 역할로 보여주기
  function renderSpeakerLabel(speaker) {
    return speakerMapping[speaker] || speaker;
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

  // 🔹 index 정보가 붙은 segments (근거 매핑에 필요)
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

  // 🔹 특정 segment index에 해당하는 OSAD 근거 태그들 구하기
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

  const osadEvidence = result?.evidence?.osad || {};

  return (
    <div
      style={{
        maxWidth: "960px",
        margin: "0 auto",
        padding: "24px",
        fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      <h1 style={{ fontSize: "24px", fontWeight: 700, marginBottom: "8px" }}>
        지도전문의 피드백 OSAD 분석 (MVP)
      </h1>
      <p style={{ marginBottom: "16px", color: "#555" }}>
        실제 서비스에서는 음성 녹음을 STT로 변환한 텍스트가 이 입력창으로
        들어올 예정입니다. 지금은 테스트를 위해 직접 피드백 문장을 입력하거나,
        위에서 음성을 녹음해 보세요.
      </p>

      {/* 🔹 1. 음성 녹음 영역 */}
      <section
        style={{
          marginBottom: "16px",
          padding: "16px",
          borderRadius: "12px",
          border: "1px solid #e5e7eb",
          backgroundColor: "#f9fafb",
        }}
      >
        <h2
          style={{
            fontSize: "18px",
            fontWeight: 600,
            marginBottom: "8px",
          }}
        >
          1. 음성 녹음하기
        </h2>
        <p style={{ fontSize: "14px", color: "#555", marginBottom: "8px" }}>
          지도전문의-전공의 피드백 장면을 이 브라우저에서 바로 녹음합니다.
          (녹음 종료 후 재생 및 STT + 화자 구분으로 텍스트로 변환할 수
          있습니다.)
        </p>
        <div style={{ display: "flex", gap: "8px", marginBottom: "8px" }}>
          <button
            type="button"
            onClick={handleStartRecording}
            disabled={isRecording}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              cursor: isRecording ? "default" : "pointer",
              fontWeight: 600,
            }}
          >
            🎙 녹음 시작
          </button>
          <button
            type="button"
            onClick={handleStopRecording}
            disabled={!isRecording}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              cursor: !isRecording ? "default" : "pointer",
              fontWeight: 600,
            }}
          >
            ⏹ 녹음 종료
          </button>
          <button
            type="button"
            onClick={handlePlayRecording}
            disabled={!audioUrl}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              cursor: audioUrl ? "pointer" : "default",
              fontWeight: 600,
            }}
          >
            ▶ 녹음 재생
          </button>
          <button
            type="button"
            onClick={handleTranscribeRecording}
            disabled={!audioChunksRef.current.length}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              cursor: audioChunksRef.current.length ? "pointer" : "default",
              fontWeight: 600,
            }}
          >
            ✨ 텍스트 변환 (화자 구분 포함)
          </button>
        </div>
        {recordingStatus && (
          <p style={{ marginTop: "4px", fontSize: "14px", color: "#111" }}>
            {recordingStatus}
          </p>
        )}
      </section>

      {/* 🔹 1-2. 화자별 transcript 미리보기 */}
      {segments && segments.length > 0 && (
        <section
          style={{
            marginBottom: "16px",
            padding: "16px",
            borderRadius: "12px",
            border: "1px solid #e5e7eb",
            backgroundColor: "#f3f4f6",
          }}
        >
          <h2
            style={{
              fontSize: "18px",
              fontWeight: 600,
              marginBottom: "8px",
            }}
          >
            1-2. 화자별 transcript (Speaker Diarization)
          </h2>

          {/* 화자 역할 매핑 */}
          {uniqueSpeakers.length > 0 && (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "12px",
                marginBottom: "12px",
                fontSize: "13px",
              }}
            >
              {uniqueSpeakers.map((spk) => (
                <div key={spk}>
                  <span style={{ marginRight: "4px" }}>{spk} → </span>
                  <select
                    value={speakerMapping[spk] || spk}
                    onChange={(e) =>
                      handleSpeakerSelectChange(spk, e.target.value)
                    }
                    style={{
                      padding: "4px 8px",
                      borderRadius: "6px",
                      border: "1px solid #d1d5db",
                      fontSize: "13px",
                    }}
                  >
                    <option value={spk}>{spk}</option>
                    <option value="지도전문의">지도전문의</option>
                    <option value="전공의">전공의</option>
                    <option value="기타">기타</option>
                  </select>
                </div>
              ))}
            </div>
          )}

          {/* segment 리스트 */}
          <div
            style={{
              display: "grid",
              gap: "8px",
              maxHeight: "260px",
              overflowY: "auto",
            }}
          >
            {indexedSegments.map((seg) => {
              const idx = seg._idx;
              const tags = getOsadTagsForSegment(idx);
              return (
                <div
                  key={idx}
                  style={{
                    padding: "8px",
                    borderRadius: "8px",
                    border: "1px solid #e5e7eb",
                    backgroundColor: "#ffffff",
                    fontSize: "13px",
                  }}
                >
                  <div
                    style={{
                      marginBottom: "4px",
                      display: "flex",
                      justifyContent: "space-between",
                      color: "#4b5563",
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>
                      {renderSpeakerLabel(seg.speaker)}
                    </span>
                    <span>
                      {seg.start?.toFixed ? seg.start.toFixed(1) : seg.start} s
                      {" ~ "}
                      {seg.end?.toFixed ? seg.end.toFixed(1) : seg.end} s
                    </span>
                  </div>
                  <div style={{ marginBottom: tags.length ? "4px" : 0 }}>
                    {seg.text}
                  </div>
                  {tags.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "4px",
                        fontSize: "11px",
                      }}
                    >
                      {tags.map((t) => (
                        <span
                          key={t}
                          style={{
                            padding: "2px 6px",
                            borderRadius: "999px",
                            backgroundColor: "#dbeafe",
                            color: "#1d4ed8",
                          }}
                        >
                          OSAD: {t}
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

      {/* 🔹 1-3. 역할별 발언 분리 (좌: 전공의, 우: 지도전문의) */}
      {segments && segments.length > 0 && (
        <section
          style={{
            marginBottom: "24px",
            padding: "16px",
            borderRadius: "12px",
            border: "1px solid #e5e7eb",
            backgroundColor: "#ffffff",
          }}
        >
          <h2
            style={{
              fontSize: "18px",
              fontWeight: 600,
              marginBottom: "8px",
            }}
          >
            1-3. 역할별 발언 분리
          </h2>
          <p style={{ fontSize: "13px", color: "#555", marginBottom: "8px" }}>
            좌측에는 전공의 발언, 우측에는 지도전문의 발언만 시간 순서대로
            모아서 보여줍니다. 나중에는 전공의 피드백 기능도 이 영역을 기반으로
            확장할 수 있습니다.
          </p>
          <div
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
            }}
          >
            {/* 전공의 발언 */}
            <div
              style={{
                flex: 1,
                borderRadius: "10px",
                border: "1px solid #e5e7eb",
                backgroundColor: "#f9fafb",
                padding: "8px 10px",
                minHeight: "80px",
              }}
            >
              <div
                style={{
                  fontSize: "14px",
                  fontWeight: 600,
                  marginBottom: "6px",
                  color: "#1f2933",
                }}
              >
                전공의 발언
              </div>
              {traineeSegments.length === 0 ? (
                <p
                  style={{
                    fontSize: "13px",
                    color: "#9ca3af",
                    fontStyle: "italic",
                  }}
                >
                  전공의로 분류된 발언이 아직 없습니다.
                </p>
              ) : (
                <div
                  style={{
                    display: "grid",
                    gap: "6px",
                    maxHeight: "200px",
                    overflowY: "auto",
                    fontSize: "13px",
                  }}
                >
                  {traineeSegments.map((seg) => {
                    const idx = seg._idx;
                    const tags = getOsadTagsForSegment(idx);
                    return (
                      <div
                        key={idx}
                        style={{
                          padding: "6px 8px",
                          borderRadius: "8px",
                          backgroundColor: "#ffffff",
                          border: "1px solid #e5e7eb",
                        }}
                      >
                        <div
                          style={{
                            marginBottom: "2px",
                            fontSize: "12px",
                            color: "#6b7280",
                          }}
                        >
                          {seg.start?.toFixed
                            ? seg.start.toFixed(1)
                            : seg.start}{" "}
                          s ~{" "}
                          {seg.end?.toFixed ? seg.end.toFixed(1) : seg.end} s
                        </div>
                        <div style={{ marginBottom: tags.length ? "4px" : 0 }}>
                          {seg.text}
                        </div>
                        {tags.length > 0 && (
                          <div
                            style={{
                              display: "flex",
                              flexWrap: "wrap",
                              gap: "4px",
                              fontSize: "11px",
                            }}
                          >
                            {tags.map((t) => (
                              <span
                                key={t}
                                style={{
                                  padding: "2px 6px",
                                  borderRadius: "999px",
                                  backgroundColor: "#dbeafe",
                                  color: "#1d4ed8",
                                }}
                              >
                                OSAD: {t}
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
            <div
              style={{
                flex: 1,
                borderRadius: "10px",
                border: "1px solid #e5e7eb",
                backgroundColor: "#f9fafb",
                padding: "8px 10px",
                minHeight: "80px",
              }}
            >
              <div
                style={{
                  fontSize: "14px",
                  fontWeight: 600,
                  marginBottom: "6px",
                  color: "#1f2933",
                }}
              >
                지도전문의 발언
              </div>
              {supervisorSegments.length === 0 ? (
                <p
                  style={{
                    fontSize: "13px",
                    color: "#9ca3af",
                    fontStyle: "italic",
                  }}
                >
                  지도전문의로 분류된 발언이 아직 없습니다.
                </p>
              ) : (
                <div
                  style={{
                    display: "grid",
                    gap: "6px",
                    maxHeight: "200px",
                    overflowY: "auto",
                    fontSize: "13px",
                  }}
                >
                  {supervisorSegments.map((seg) => {
                    const idx = seg._idx;
                    const tags = getOsadTagsForSegment(idx);
                    return (
                      <div
                        key={idx}
                        style={{
                          padding: "6px 8px",
                          borderRadius: "8px",
                          backgroundColor: "#ffffff",
                          border: "1px solid #e5e7eb",
                        }}
                      >
                        <div
                          style={{
                            marginBottom: "2px",
                            fontSize: "12px",
                            color: "#6b7280",
                          }}
                        >
                          {seg.start?.toFixed
                            ? seg.start.toFixed(1)
                            : seg.start}{" "}
                          s ~{" "}
                          {seg.end?.toFixed ? seg.end.toFixed(1) : seg.end} s
                        </div>
                        <div style={{ marginBottom: tags.length ? "4px" : 0 }}>
                          {seg.text}
                        </div>
                        {tags.length > 0 && (
                          <div
                            style={{
                              display: "flex",
                              flexWrap: "wrap",
                              gap: "4px",
                              fontSize: "11px",
                            }}
                          >
                            {tags.map((t) => (
                              <span
                                key={t}
                                style={{
                                  padding: "2px 6px",
                                  borderRadius: "999px",
                                  backgroundColor: "#dbeafe",
                                  color: "#1d4ed8",
                                }}
                              >
                                OSAD: {t}
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

      {/* 🔹 2. 텍스트 입력 + OSAD 분석 */}
      <form onSubmit={handleAnalyze}>
        <label
          htmlFor="transcript"
          style={{ display: "block", fontWeight: 600, marginBottom: "8px" }}
        >
          2. 피드백 대화 transcript
        </label>
        <textarea
          id="transcript"
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          rows={8}
          style={{
            width: "100%",
            padding: "12px",
            fontSize: "14px",
            lineHeight: 1.5,
            borderRadius: "8px",
            border: "1px solid " + (error ? "#f97373" : "#ccc"),
            resize: "vertical",
            boxSizing: "border-box",
          }}
        />

        <div style={{ marginTop: "12px", display: "flex", gap: "8px" }}>
          <button
            type="submit"
            disabled={loading || !transcript.trim()}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              cursor: loading ? "default" : "pointer",
              fontWeight: 600,
              backgroundColor: loading ? "#aaa" : "#2563eb",
              color: "white",
            }}
          >
            {loading ? "분석 중..." : "OSAD 분석하기"}
          </button>
        </div>
      </form>

      {error && (
        <div
          style={{
            marginTop: "16px",
            padding: "12px",
            borderRadius: "8px",
            backgroundColor: "#fee2e2",
            color: "#b91c1c",
            whiteSpace: "pre-wrap",
            fontSize: "14px",
          }}
        >
          오류: {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: "24px", display: "grid", gap: "16px" }}>
          {/* OSAD 점수 요약 */}
          <section
            style={{
              padding: "16px",
              borderRadius: "12px",
              border: "1px solid #e5e7eb",
              backgroundColor: "#f9fafb",
            }}
          >
            <h2
              style={{
                fontSize: "18px",
                fontWeight: 600,
                marginBottom: "8px",
              }}
            >
              OSAD 점수
            </h2>
            <p style={{ marginBottom: "8px", fontSize: "14px", color: "#555" }}>
              총점: <strong>{result.osad.total}</strong> / {result.osad.scale}
            </p>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                gap: "4px 12px",
                fontSize: "13px",
              }}
            >
              {[
                "approach",
                "learning_env",
                "engagement",
                "reaction",
                "reflection",
                "analysis",
                "diagnosis",
                "application",
                "summary",
              ].map((key) => (
                <div
                  key={key}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    borderBottom: "1px dashed #e5e7eb",
                    paddingBottom: "2px",
                  }}
                >
                  <span>{key}</span>
                  <span>{result.osad[key]}</span>
                </div>
              ))}
            </div>
            {/* 근거가 있는 OSAD 차원 목록 간단 표시 */}
            {Object.keys(osadEvidence).length > 0 && (
              <p
                style={{
                  marginTop: "8px",
                  fontSize: "12px",
                  color: "#4b5563",
                }}
              >
                * 파란 OSAD 태그가 붙은 segment는 해당 차원의 근거로 사용된
                발언입니다.
              </p>
            )}
          </section>

          {/* 구조 분석 */}
          <section
            style={{
              padding: "16px",
              borderRadius: "12px",
              border: "1px solid #e5e7eb",
              backgroundColor: "#f9fafb",
            }}
          >
            <h2
              style={{
                fontSize: "18px",
                fontWeight: 600,
                marginBottom: "8px",
              }}
            >
              구조 분석 (Opening / Core / Closing)
            </h2>
            <ul style={{ listStyle: "none", paddingLeft: 0, fontSize: "14px" }}>
              <li>
                {result.structure.has_opening ? "✅" : "❌"} Opening (전공의
                의견/생각을 묻는 시작)
              </li>
              <li>
                {result.structure.has_core ? "✅" : "❌"} Core (관찰·이유·결과 등
                핵심 내용)
              </li>
              <li>
                {result.structure.has_closing ? "✅" : "❌"} Closing (요약·다음
                단계 제시)
              </li>
            </ul>
          </section>

          {/* 코칭 리포트 */}
          <section
            style={{
              padding: "16px",
              borderRadius: "12px",
              border: "1px solid #e5e7eb",
              backgroundColor: "#f9fafb",
            }}
          >
            <h2
              style={{
                fontSize: "18px",
                fontWeight: 600,
                marginBottom: "8px",
              }}
            >
              코칭 리포트
            </h2>

            <div style={{ marginBottom: "12px" }}>
              <h3
                style={{
                  fontSize: "15px",
                  fontWeight: 600,
                  marginBottom: "4px",
                }}
              >
                강점 (Strengths)
              </h3>
              <ul style={{ paddingLeft: "18px", fontSize: "14px" }}>
                {result.coach.strengths.map((s, idx) => (
                  <li key={idx}>{s}</li>
                ))}
              </ul>
            </div>

            <div style={{ marginBottom: "12px" }}>
              <h3
                style={{
                  fontSize: "15px",
                  fontWeight: 600,
                  marginBottom: "4px",
                }}
              >
                개선이 필요한 상위 3가지 (Improvements)
              </h3>
              <ul style={{ paddingLeft: "18px", fontSize: "14px" }}>
                {result.coach.improvements_top3.map((s, idx) => (
                  <li key={idx}>{s}</li>
                ))}
              </ul>
            </div>

            <div style={{ marginBottom: "8px" }}>
              <h3
                style={{
                  fontSize: "15px",
                  fontWeight: 600,
                  marginBottom: "4px",
                }}
              >
                다음에 이렇게 말해보세요 (Script next time)
              </h3>
              <p style={{ fontSize: "14px", whiteSpace: "pre-wrap" }}>
                {result.coach.script_next_time}
              </p>
            </div>

            <div>
              <h3
                style={{
                  fontSize: "15px",
                  fontWeight: 600,
                  marginBottom: "4px",
                }}
              >
                10초짜리 미세 습관 (Micro habit)
              </h3>
              <p style={{ fontSize: "14px", whiteSpace: "pre-wrap" }}>
                {result.coach.micro_habit_10sec}
              </p>
            </div>
          </section>

          {/* 디버깅용 Raw JSON */}
          <section
            style={{
              padding: "16px",
              borderRadius: "12px",
              border: "1px solid #e5e7eb",
              backgroundColor: "#111",
              color: "#e5e7eb",
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas",
              fontSize: "12px",
              overflowX: "auto",
            }}
          >
            <h2
              style={{
                fontSize: "15px",
                fontWeight: 600,
                marginBottom: "8px",
              }}
            >
              Raw JSON (디버깅용)
            </h2>
            <pre style={{ margin: 0 }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
