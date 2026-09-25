import { Navigate, Route, Routes } from "react-router-dom";

import { ContactCheckPage } from "@/pages/ContactCheckPage";
import { ContactResultPage } from "@/pages/ContactResultPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { WelcomePage } from "@/pages/WelcomePage";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Navigate replace to="/welcome" />} />
      <Route path="/welcome" element={<WelcomePage />} />
      <Route path="/demo" element={<WelcomePage />} />
      <Route path="/check" element={<ContactCheckPage />} />
      <Route
        path="/checks/:observationId/:incidentId/:assessmentId"
        element={<ContactResultPage />}
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
