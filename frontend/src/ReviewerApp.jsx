import { useEffect, useMemo, useState } from "react";

let API_BASE;

if (
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1")
) {
  // 로컬 개발 환경
  API_BASE = "http://127.0.0.1:8000";
} else {
  // 인터넷 배포 환경
  API_BASE = "https://feedback-trainer-mvp-1.onrender.com";
}

console.log("[DEBUG][ReviewerApp] API_BASE =", API_BASE);


function getReviewerToken() {
  return sessionStorage.getItem("reviewer_token") || "";
}

function reviewerHeaders() {
  const token = getReviewerToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const OMP_ITEMS = [
  ["get_commitment", "1. 판단 유도"],
  ["probe_for_supporting_evidence", "2. 근거 탐색"],
  ["teach_general_rules", "3. 일반 원칙 교육"],
  ["reinforce_what_was_done_right", "4. 잘한 점 강화"],
  ["correct_mistakes", "5. 개선점 교정"],
];

const DEFAULT_SCORES = {
  get_commitment: 3,
  probe_for_supporting_evidence: 3,
  teach_general_rules: 3,
  reinforce_what_was_done_right: 3,
  correct_mistakes: 3,
};

function ReviewerApp() {
  const [raterId, setRaterId] = useState("RATER-001");
  const [activeRaterId, setActiveRaterId] = useState("RATER-001");

  const [mode, setMode] = useState("pending"); // pending | completed
  const [pendingSessions, setPendingSessions] = useState([]);
  const [completedSessions, setCompletedSessions] = useState([]);
  const [selectedCompletedId, setSelectedCompletedId] = useState("");

  const [scores, setScores] = useState(DEFAULT_SCORES);
  const [comment, setComment] = useState("");

  const [progress, setProgress] = useState({
    total: 0,
    completed: 0,
    remaining: 0,
    percent: 0,
  });

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [authChecking, setAuthChecking] = useState(true);

  const currentPending = pendingSessions[0] || null;

  const selectedCompleted =
    completedSessions.find(
      (item) => item.encounter_id === selectedCompletedId
    ) || completedSessions[0] || null;

  const current =
    mode === "completed" ? selectedCompleted : currentPending;

  const total = useMemo(
    () => Object.values(scores).reduce((sum, v) => sum + Number(v || 0), 0),
    [scores]
  );

  function resetForm() {
    setScores(DEFAULT_SCORES);
    setComment("");
    setMessage("");
    setError("");
  }

  function loadRatingIntoForm(session) {
    const rating = session?.rating;

    if (!rating) {
      setScores(DEFAULT_SCORES);
      setComment("");
      return;
    }

    setScores({
      get_commitment: Number(rating.get_commitment || 3),
      probe_for_supporting_evidence: Number(
        rating.probe_for_supporting_evidence || 3
      ),
      teach_general_rules: Number(rating.teach_general_rules || 3),
      reinforce_what_was_done_right: Number(
        rating.reinforce_what_was_done_right || 3
      ),
      correct_mistakes: Number(rating.correct_mistakes || 3),
    });
    setComment(rating.comment || "");
  }

  async function fetchSessionSet(cleanRaterId, completedOnly) {
    const params = new URLSearchParams({
      rater_id: cleanRaterId,
      include_completed: completedOnly ? "true" : "false",
      completed_only: completedOnly ? "true" : "false",
      limit: "1000",
      offset: "0",
    });

    const res = await fetch(
      `${API_BASE}/api/reviewer/sessions?${params.toString()}`,
      {
        cache: "no-store",
        headers: reviewerHeaders(),
      }
    );

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`세션 조회 실패: ${res.status} - ${body}`);
    }

    return res.json();
  }

  async function loadSessions(requestedRaterId = activeRaterId) {
    const cleanRaterId = requestedRaterId.trim();

    if (!cleanRaterId) {
      setError("평가자 ID를 입력해 주세요.");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const [pendingData, completedData] = await Promise.all([
        fetchSessionSet(cleanRaterId, false),
        fetchSessionSet(cleanRaterId, true),
      ]);

      const pending = Array.isArray(pendingData.items)
        ? pendingData.items
        : [];
      const completed = Array.isArray(completedData.items)
        ? completedData.items
        : [];

      setActiveRaterId(cleanRaterId);
      setRaterId(cleanRaterId);
      setPendingSessions(pending);
      setCompletedSessions(completed);

      setProgress({
        total: Number(pendingData.total_sessions || 0),
        completed: Number(pendingData.completed_count || 0),
        remaining: Number(pendingData.remaining_count || 0),
        percent: Number(pendingData.completion_percent || 0),
      });

      if (
        selectedCompletedId &&
        completed.some((x) => x.encounter_id === selectedCompletedId)
      ) {
        const selected = completed.find(
          (x) => x.encounter_id === selectedCompletedId
        );
        if (mode === "completed") loadRatingIntoForm(selected);
      } else if (completed.length > 0) {
        setSelectedCompletedId(completed[0].encounter_id);
        if (mode === "completed") loadRatingIntoForm(completed[0]);
      } else {
        setSelectedCompletedId("");
        if (mode === "completed") resetForm();
      }

      if (mode === "pending") resetForm();
    } catch (err) {
      console.error(err);
      setError(err.message || "세션 목록을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    async function verifyAccess() {
      const token = getReviewerToken();

      if (!token) {
        window.location.href = "/";
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/api/reviewer-auth/verify`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });

        if (!res.ok) {
          sessionStorage.removeItem("reviewer_token");
          sessionStorage.removeItem("reviewer_token_expires_at");
          window.location.href = "/";
          return;
        }

        setAuthChecking(false);
        await loadSessions("RATER-001");
      } catch (err) {
        console.error(err);
        setError("평가자 인증 상태를 확인하지 못했습니다.");
        setAuthChecking(false);
      }
    }

    verifyAccess();
  }, []);

  useEffect(() => {
    if (mode === "completed" && selectedCompleted) {
      loadRatingIntoForm(selectedCompleted);
      setMessage("");
      setError("");
    }

    if (mode === "pending") {
      resetForm();
    }
  }, [mode, selectedCompletedId]);

  async function saveRating() {
    if (!current) {
      setError("평가할 세션이 없습니다.");
      return;
    }

    const cleanRaterId = activeRaterId.trim();

    if (!cleanRaterId) {
      setError("평가자 ID를 먼저 확정해 주세요.");
      return;
    }

    setSaving(true);
    setError("");
    setMessage("");

    try {
      const payload = {
        encounter_id: current.encounter_id,
        rater_id: cleanRaterId,
        get_commitment: scores.get_commitment,
        probe_for_supporting_evidence: scores.probe_for_supporting_evidence,
        teach_general_rules: scores.teach_general_rules,
        reinforce_what_was_done_right: scores.reinforce_what_was_done_right,
        correct_mistakes: scores.correct_mistakes,
        comment: comment.trim() || null,
      };

      const res = await fetch(`${API_BASE}/api/reviewer/human-ratings`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...reviewerHeaders(),
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await res.text();
        throw new Error(`평가 저장 실패: ${res.status} - ${body}`);
      }

      const savedEncounterId = current.encounter_id;
      await loadSessions(cleanRaterId);

      if (mode === "completed") {
        setSelectedCompletedId(savedEncounterId);
        setMessage("평가 내용이 수정 저장되었습니다.");
      } else {
        setMessage(
          "평가가 저장되었습니다. 다음 미평가 세션으로 이동했습니다."
        );
      }
    } catch (err) {
      console.error(err);
      setError(err.message || "평가 저장 중 오류가 발생했습니다.");
    } finally {
      setSaving(false);
    }
  }

  function logoutReviewer() {
    sessionStorage.removeItem("reviewer_token");
    sessionStorage.removeItem("reviewer_token_expires_at");
    window.location.href = "/";
  }

  function transcriptPreview(item) {
    const txt = String(item?.transcript || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!txt) return "(transcript 없음)";
    return txt.length > 90 ? `${txt.slice(0, 90)}…` : txt;
  }

  if (authChecking) {
    return (
      <div style={{ maxWidth: 760, margin: "40px auto", padding: 24 }}>
        평가자 인증을 확인하고 있습니다...
      </div>
    );
  }

  return (
    <div
      style={{
        maxWidth: 1100,
        margin: "0 auto",
        padding: 24,
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 style={{ marginBottom: 6 }}>OMP 인간 평가</h1>
          <p style={{ color: "#555", marginTop: 0 }}>
            저장된 피드백 transcript를 AI 결과 없이 독립적으로 평가합니다.
          </p>
        </div>

        <button onClick={logoutReviewer} style={{ padding: "8px 12px" }}>
          평가 종료
        </button>
      </div>

      <section
        style={{
          border: "1px solid #ddd",
          borderRadius: 8,
          padding: 16,
          marginBottom: 16,
        }}
      >
        <div
          style={{
            display: "flex",
            gap: 12,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <label>
            <strong>평가자 ID</strong>{" "}
            <input
              value={raterId}
              onChange={(e) => setRaterId(e.target.value)}
              style={{ padding: 8, minWidth: 180 }}
              disabled={loading || saving}
            />
          </label>

          <button
            onClick={() => loadSessions(raterId)}
            disabled={loading || saving}
            style={{ padding: "8px 14px" }}
          >
            {loading ? "불러오는 중..." : "평가자 확정 / 새로고침"}
          </button>
        </div>

        <div
          style={{
            marginTop: 16,
            display: "grid",
            gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
            gap: 10,
          }}
        >
          <div style={{ padding: 12, background: "#f8fafc", borderRadius: 6 }}>
            <div style={{ color: "#64748b", fontSize: 12 }}>전체 세션</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              {progress.total}
            </div>
          </div>

          <div style={{ padding: 12, background: "#f8fafc", borderRadius: 6 }}>
            <div style={{ color: "#64748b", fontSize: 12 }}>평가 완료</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              {progress.completed}
            </div>
          </div>

          <div style={{ padding: 12, background: "#f8fafc", borderRadius: 6 }}>
            <div style={{ color: "#64748b", fontSize: 12 }}>남은 세션</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              {progress.remaining}
            </div>
          </div>
        </div>

        <div style={{ marginTop: 12 }}>
          <div
            style={{
              height: 8,
              background: "#e5e7eb",
              borderRadius: 999,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.max(0, Math.min(100, progress.percent))}%`,
                height: "100%",
                background: "#2563eb",
              }}
            />
          </div>
          <div style={{ marginTop: 6, color: "#64748b", fontSize: 12 }}>
            진행률 {progress.completed} / {progress.total} ({progress.percent}%)
          </div>
        </div>
      </section>

      <div
        style={{
          display: "flex",
          gap: 8,
          marginBottom: 16,
          borderBottom: "1px solid #ddd",
        }}
      >
        <button
          onClick={() => setMode("pending")}
          style={{
            padding: "10px 14px",
            border: 0,
            borderBottom:
              mode === "pending" ? "3px solid #2563eb" : "3px solid transparent",
            background: "transparent",
            fontWeight: mode === "pending" ? 700 : 400,
          }}
        >
          미평가 ({progress.remaining})
        </button>

        <button
          onClick={() => setMode("completed")}
          style={{
            padding: "10px 14px",
            border: 0,
            borderBottom:
              mode === "completed"
                ? "3px solid #2563eb"
                : "3px solid transparent",
            background: "transparent",
            fontWeight: mode === "completed" ? 700 : 400,
          }}
        >
          평가 완료 ({progress.completed})
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: 10,
            background: "#fee2e2",
            color: "#991b1b",
            marginBottom: 12,
          }}
        >
          {error}
        </div>
      )}

      {message && (
        <div
          style={{
            padding: 10,
            background: "#ecfdf5",
            color: "#065f46",
            marginBottom: 12,
          }}
        >
          {message}
        </div>
      )}

      {mode === "completed" && (
        <section
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
            marginBottom: 16,
          }}
        >
          <h2 style={{ marginTop: 0 }}>평가 완료 피드백 목록</h2>

          {completedSessions.length === 0 ? (
            <div style={{ color: "#64748b" }}>
              아직 완료된 평가가 없습니다.
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gap: 8,
                maxHeight: 300,
                overflowY: "auto",
              }}
            >
              {completedSessions.map((item, idx) => {
                const selected =
                  selectedCompleted?.encounter_id === item.encounter_id;

                return (
                  <button
                    key={item.encounter_id}
                    type="button"
                    onClick={() => setSelectedCompletedId(item.encounter_id)}
                    style={{
                      textAlign: "left",
                      padding: 12,
                      borderRadius: 6,
                      border: selected
                        ? "2px solid #2563eb"
                        : "1px solid #ddd",
                      background: selected ? "#eff6ff" : "#fff",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ fontWeight: 700 }}>
                      {idx + 1}. {item.encounter_id}
                    </div>
                    <div
                      style={{
                        marginTop: 5,
                        color: "#475569",
                        fontSize: 13,
                        lineHeight: 1.4,
                      }}
                    >
                      {transcriptPreview(item)}
                    </div>
                    {item.rating && (
                      <div
                        style={{
                          marginTop: 5,
                          color: "#64748b",
                          fontSize: 12,
                        }}
                      >
                        저장된 OMP 총점 {item.rating.omp_total} / 25
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </section>
      )}

      {!current ? (
        <div
          style={{
            padding: 24,
            border: "1px solid #ddd",
            borderRadius: 8,
            textAlign: "center",
          }}
        >
          {mode === "pending" && progress.total > 0 && progress.remaining === 0
            ? `${activeRaterId} 평가가 모두 완료되었습니다.`
            : mode === "completed"
            ? "확인할 완료 평가가 없습니다."
            : "현재 평가할 미평가 세션이 없습니다."}
        </div>
      ) : (
        <>
          <section
            style={{
              border: "1px solid #ddd",
              borderRadius: 8,
              padding: 16,
              marginBottom: 16,
            }}
          >
            <div>
              <strong>
                {mode === "completed"
                  ? "완료 평가 다시 보기"
                  : `미평가 세션 ${progress.completed + 1} / ${progress.total}`}
              </strong>
              <div style={{ marginTop: 4 }}>
                <code>{current.encounter_id}</code>
              </div>
            </div>
          </section>

          <section
            style={{
              border: "1px solid #ddd",
              borderRadius: 8,
              padding: 16,
              marginBottom: 16,
            }}
          >
            <h2 style={{ marginTop: 0 }}>피드백 transcript</h2>

            {Array.isArray(current.segments) && current.segments.length > 0 ? (
              <div
                style={{
                  lineHeight: 1.7,
                  minHeight: 160,
                  padding: 14,
                  background: "#f8fafc",
                  borderRadius: 6,
                }}
              >
                {current.segments.map((seg, idx) => (
                  <div key={idx} style={{ marginBottom: 10 }}>
                    <strong>{seg.speaker || `SPEAKER_${idx}`}:</strong>{" "}
                    {seg.text || ""}
                  </div>
                ))}
              </div>
            ) : (
              <div
                style={{
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.7,
                  minHeight: 160,
                  padding: 14,
                  background: "#f8fafc",
                  borderRadius: 6,
                }}
              >
                {current.transcript || "표시할 transcript가 없습니다."}
              </div>
            )}

            <p style={{ color: "#64748b", fontSize: 12, marginBottom: 0 }}>
              AI OMP 점수, AI 코칭 결과, AI 화자 역할 추론은 표시되지 않습니다.
            </p>
          </section>

          <section
            style={{
              border: "1px solid #ddd",
              borderRadius: 8,
              padding: 16,
            }}
          >
            <h2 style={{ marginTop: 0 }}>
              {mode === "completed"
                ? "저장된 OMP 평가 확인 / 수정"
                : "OMP 5개 microskill 평가"}
            </h2>

            <div style={{ display: "grid", gap: 12 }}>
              {OMP_ITEMS.map(([key, label]) => (
                <div
                  key={key}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 16,
                    alignItems: "center",
                    borderBottom: "1px solid #eee",
                    paddingBottom: 10,
                  }}
                >
                  <span>{label}</span>

                  <select
                    value={scores[key]}
                    onChange={(e) =>
                      setScores((prev) => ({
                        ...prev,
                        [key]: Number(e.target.value),
                      }))
                    }
                    style={{ padding: 8, width: 90 }}
                    disabled={saving}
                  >
                    {[1, 2, 3, 4, 5].map((score) => (
                      <option key={score} value={score}>
                        {score}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 16, fontWeight: 700 }}>
              총점: {total} / 25
            </div>

            <div style={{ marginTop: 16 }}>
              <label>
                <strong>평가자 메모 (선택)</strong>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={4}
                  style={{
                    width: "100%",
                    marginTop: 8,
                    padding: 10,
                    boxSizing: "border-box",
                  }}
                  disabled={saving}
                />
              </label>
            </div>

            <button
              onClick={saveRating}
              disabled={saving}
              style={{
                marginTop: 16,
                width: "100%",
                padding: "12px 18px",
                background: saving ? "#93c5fd" : "#2563eb",
                color: "#fff",
                border: 0,
                borderRadius: 6,
                cursor: saving ? "default" : "pointer",
                fontWeight: 700,
              }}
            >
              {saving
                ? "저장 중..."
                : mode === "completed"
                ? "수정 내용 저장하기"
                : "평가 저장하고 다음 미평가 세션"}
            </button>
          </section>
        </>
      )}
    </div>
  );
}

export default ReviewerApp;
