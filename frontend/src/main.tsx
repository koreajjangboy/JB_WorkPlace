import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import App from "./App";
import "./index.css";
import HomePage from "./pages/HomePage";
import ProjectChangesPage from "./pages/ProjectChangesPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import ProjectsPage from "./pages/ProjectsPage";
import NewTaskPage from "./pages/NewTaskPage";
import SessionPage from "./pages/SessionPage";
import TaskDetailPage from "./pages/TaskDetailPage";
import TasksPage from "./pages/TasksPage";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<HomePage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="projects/:projectId/changes" element={<ProjectChangesPage />} />
          <Route path="sessions/:sessionId" element={<SessionPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="tasks/new" element={<NewTaskPage />} />
          <Route path="tasks/:taskId" element={<TaskDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
