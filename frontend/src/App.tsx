import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { LoadingState } from "./components/Common";

const AboutPage = lazy(() => import("./pages/AboutPage"));
const ApiPage = lazy(() => import("./pages/ApiPage"));
const ArchitecturePage = lazy(() => import("./pages/ArchitecturePage"));
const ExplorePage = lazy(() => import("./pages/ExplorePage"));
const HarmonizationPage = lazy(() => import("./pages/HarmonizationPage"));
const HomePage = lazy(() => import("./pages/HomePage"));
const MetadataPage = lazy(() => import("./pages/MetadataPage"));
const ValidationPage = lazy(() => import("./pages/ValidationPage"));

export default function App() {
  return (
    <Suspense fallback={<div className="page-width page-content"><LoadingState label="Loading page…" /></div>}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="explore" element={<ExplorePage />} />
          <Route path="metadata" element={<MetadataPage />} />
          <Route path="validation" element={<ValidationPage />} />
          <Route path="harmonization" element={<HarmonizationPage />} />
          <Route path="architecture" element={<ArchitecturePage />} />
          <Route path="api" element={<ApiPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
