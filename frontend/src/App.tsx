import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Header } from "./components/Header";
import { SubmitPage } from "./pages/SubmitPage";
import { JobStatusPage } from "./pages/JobStatusPage";
import { JobResultPage } from "./pages/JobResultPage";
import { ReportPage } from "./pages/ReportPage";
import { HistoryPage } from "./pages/HistoryPage";
import { ThemeProvider } from "./ThemeContext";
import "./App.css";

function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Header />
        <main>
          <Routes>
            <Route path="/" element={<SubmitPage />} />
            <Route path="/jobs/:jobId" element={<JobStatusPage />} />
            <Route path="/jobs/:jobId/view" element={<JobResultPage />} />
            <Route path="/jobs/:jobId/report" element={<ReportPage />} />
            <Route path="/history" element={<HistoryPage />} />
          </Routes>
        </main>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
