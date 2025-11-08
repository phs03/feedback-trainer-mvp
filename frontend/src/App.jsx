import { useState } from "react";
import axios from "axios";
// import Recorder from "./components/Recorder.jsx"; // 녹음도 쓰려면 주석 해제

export default function App() {
  const [txt, setTxt] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  async function analyze() {
    if (!txt || txt.trim().length < 5) { alert("문장을 입력하세요."); return; }
    setLoading(true);
    try {
      const res = await axios.post("http://127.0.0.1:8000/api/feedback", {
        transcript: txt, trainee_level: "PGY-2", language: "ko"
      });
      setResult(res.data);
    } catch (e) {
      alert("분석 실패: " + (e?.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  async function downloadPdf() {
    if (!result) { alert("분석 결과가 없습니다."); return; }
    const res = await axios.post("http://127.0.0.1:8000/api/report", result, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "OSAD_Report.pdf";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div style={{ fontFamily: "system-ui, Arial", padding: 24, maxWidth: 900 }}>
      <h1>AI Feedback MVP</h1>

      <h3>1) 전사 텍스트 또는 예시 문장 입력</h3>
      {/* <Recorder onTranscribed={(t) => setTxt(t)} /> */}
      <textarea
        style={{ width: "100%", height: 140 }}
        value={txt}
        onChange={(e) => setTxt(e.target.value)}
        placeholder="여기에 전사 텍스트(또는 예시 문장)를 붙여넣으세요."
      />
      <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
        <button onClick={analyze} disabled={loading}>
          {loading ? "분석 중..." : "OSAD 분석 실행"}
        </button>
        <button onClick={downloadPdf} disabled={!result}>PDF 다운로드</button>
      </div>

      {result && (
        <div style={{ marginTop: 16 }}>
          <h3>요약</h3>
          <p>{result.summary}</p>

          <h3>도메인 점수</h3>
          <table border="1" cellPadding="6">
            <thead>
              <tr>
                <th>Domain</th><th>Score</th><th>Evidence</th><th>Suggestion</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.domains || {}).map(([k, v]) => (
                <tr key={k}>
                  <td><b>{k}</b></td>
                  <td>{v.score}</td>
                  <td>{v.evidence}</td>
                  <td>{v.suggestion}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>종합</h3>
          <p><b>Strengths</b>: {result.overall?.strengths?.join("; ")}</p>
          <p><b>Improvements</b>: {result.overall?.improvements?.join("; ")}</p>
          <p><b>Action Plan</b>: {result.overall?.action_plan?.join(" → ")}</p>
        </div>
      )}
    </div>
  );
}
