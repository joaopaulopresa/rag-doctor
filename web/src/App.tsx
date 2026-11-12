import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import Chat from "./pages/Chat";
import Login from "./pages/Login";
import AdminLayout from "./pages/admin/AdminLayout";
import Case from "./pages/admin/Case";
import Compare from "./pages/admin/Compare";
import Configurations from "./pages/admin/Configurations";
import Doctor from "./pages/admin/Doctor";
import Documents from "./pages/admin/Documents";
import Examination from "./pages/admin/Examination";
import ExperimentDetail from "./pages/admin/ExperimentDetail";
import Experiments from "./pages/admin/Experiments";
import External from "./pages/admin/External";
import Playground from "./pages/admin/Playground";
import Questions from "./pages/admin/Questions";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Chat />} />
          <Route path="/login" element={<Login />} />
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="/admin/doctor" replace />} />
            <Route path="doctor" element={<Doctor />} />
            <Route path="doctor/:id" element={<Examination />} />
            <Route path="cases/:id" element={<Case />} />
            <Route path="compare" element={<Compare />} />
            <Route path="external" element={<External />} />
            <Route path="experiments" element={<Experiments />} />
            <Route path="experiments/:id" element={<ExperimentDetail />} />
            <Route path="playground" element={<Playground />} />
            <Route path="configurations" element={<Configurations />} />
            <Route path="documents" element={<Documents />} />
            <Route path="questions" element={<Questions />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
