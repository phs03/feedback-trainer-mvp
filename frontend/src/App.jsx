import { useState, useRef } from "react";

// 🔧 배포/개발 공통 API BASE 설정
const rawApiBase = import.meta.env.VITE_API_BASE_URL;
const API_BASE =
  (rawApiBase && rawApiBase.trim().replace(/\/+$/, "")) ||
  "http://127.0.0.1:8000";

const IS_DEV = import.meta.env.DEV;

function App() {
  const [transcript, setTranscript] = useState(
    "먼저 너 생각은 어땠어? 나는 네가 ABC를 설명한 건 좋았다고 생각해. 아까 환자에게 문제를 설명했을 때, 네가 쉬운 말로 바꿔서 말한 점이 특히 좋았어. 정리하면 중요한 건 감별진단의 우선순위를 환자에게도 이해할 수 있게 설명하는 거야. 다음에는 처음 5분 안에 네 가설을 한 번 말해보고, 그걸 환자에게도 공유해보자."
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  // 🔹 녹음 관련 상태
  const [isRecording, setIsRecording] = useState(false);
  const [recordingStatus, setRecordingStatus] = useState("");

  // 🔹 녹음 재생용
  const [audioUrl, setAudioUrl] = useState("");
  const audioPlayerRef = useRef(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // 🔁 화면/저장소 초기화
  function handleReset() {
    if (audioUrl) {
      try {
        URL.revokeObjectURL(audioUrl);
      } catch (e) {
        console.warn("오디오 URL 해제 중 오류:", e);
      }
    }

    setTranscript("");
    setLoading(false);
    setError("");
    setResult(null);
    setIsRecording(false);
    setRecordingStatus("");
    setAudioUrl("");
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];

    try {
      if (window.localStorage) {
        window.localStorage.clear();
      }
      if (window.sessionStorage) {
        window.sessionStorage.clear();
      }
    } catch (e) {
      console.warn("storage clear 실패:", e);
    }

    console.log("🧹 상태 및 브라우저 저장소 초기화 완료");
  }

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
      };

      const res = await fetch(`${API_BASE}/feedback`, {
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
    setRecordingStatus("");

    if (audioUrl) {
      try {
        URL.revokeObjectURL(audioUrl);
      } catch (e) {
        console.warn("오디오 URL 해제 중 오류:", e);
      }
      setAudioUrl("");
    }

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
      };

      mediaRecorder.onstop = async () => {
        setIsRecording(false);
        setRecordingStatus("🎧 녹음 완료! 텍스트 변환 준비 중...");

        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });

        console.log("녹음된 Blob:", audioBlob);

        // 브라우저 재생용 URL
        const url = URL.createObjectURL(audioBlob);
        setAudioUrl(url);
        setRecordingStatus(
          "🎧 녹음 완료! [녹음 다시 듣기]로 확인한 뒤, STT 결과를 아래에서 확인하세요."
        );

        // 🔥 STT 요청 (/api/stt, 필드 이름: file)
        try {
          const fd = new FormData();
          fd.append("file", audioBlob, "recording.webm");

          const res = await fetch(`${API_BASE}/api/stt`, {
            method: "POST",
            body: fd,
            cache: "no-store",
          });

          if (!res.ok) {
            const text = await res.text();
            throw new Error(
              `STT 요청 실패(2차): ${res.status} - ${text ?? "no body"}`
            );
          }

          const data = await res.json();
          console.log("STT 응답:", data);

          if (data && (data.transcript || data.text)) {
            setTranscript(data.transcript || data.text);
            setRecordingStatus(
              "✅ 텍스트 변환 완료! 아래 입력창에서 확인하세요."
            );
          } else {
            setRecordingStatus("⚠ 텍스트를 찾지 못했습니다.");
          }
        } catch (err) {
          console.error(err);
          setRecordingStatus("❌ 음성 → 텍스트 변환 실패");
          setError(err.message || "STT 중 오류가 발생했습니다.");
        } finally {
          const mr = mediaRecorderRef.current;
          if (mr && mr.stream) {
            mr.stream.getTracks().forEach((track) => track.stop());
          }
        }
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
    if (audioPlayerRef.current) {
      audioPlayerRef.current.play();
    }
  }

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

      {/* 개발 모드용 API Base 표시 (배포 시에는 DEV가 false라 안 보임) */}
      {IS_DEV && (
        <div
          style={{
            marginBottom: "8px",
            fontSize: "11px",
            color: "#4b5563",
            backgroundColor: "#e5e7eb",
            display: "inline-block",
            padding: "4px 8px",
            borderRadius: "999px",
          }}
        >
          API_BASE: {API_BASE}
        </div>
      )}

      {/* 🔁 전체 초기화 버튼 */}
      <div style={{ marginBottom: "12px", display: "flex", gap: "8px" }}>
        <button
          type="button"
          onClick={handleReset}
          style={{
            padding: "6px 12px",
            borderRadius: "8px",
            border: "1px solid #e5e7eb",
            backgroundColor: "#f3f4f6",
            cursor: "pointer",
            fontSize: "13px",
            fontWeight: 600,
          }}
        >
          🔄 화면/저장소 초기화
        </button>
      </div>

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
          (녹음 종료 후 Whisper STT로 텍스트로 변환됩니다.)
        </p>
        <div style={{ display: "flex", gap: "8px" }}>
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
        </div>

        {/* 녹음 다시 듣기 + 플레이어 */}
        {audioUrl && (
          <div style={{ marginTop: "12px" }}>
            <button
              type="button"
              onClick={handlePlayRecording}
              style={{
                padding: "8px 16px",
                borderRadius: "8px",
                border: "none",
                cursor: "pointer",
                fontWeight: 600,
                marginBottom: "8px",
              }}
            >
              ▶ 녹음 다시 듣기
            </button>
            <audio
              ref={audioPlayerRef}
              src={audioUrl}
              controls
              style={{ width: "100%" }}
            />
          </div>
        )}

        {recordingStatus && (
          <p style={{ marginTop: "8px", fontSize: "14px", color: "#111" }}>
            {recordingStatus}
          </p>
        )}
      </section>

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
            borderRadius: "12px",
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
