import { Navigate, Route, Routes } from "react-router-dom";

import { NotFoundPage } from "@/pages/NotFoundPage";
import { WelcomePage } from "@/pages/WelcomePage";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Navigate replace to="/welcome" />} />
      <Route path="/welcome" element={<WelcomePage />} />
      <Route path="/demo" element={<WelcomePage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
