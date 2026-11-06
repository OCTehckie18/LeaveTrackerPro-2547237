import { Route, Routes } from "react-router-dom";
import { RequireAuth, RequireRole } from "./components/Layout";
import Apply from "./pages/Apply";
import Dashboard from "./pages/Dashboard";
import LeaveDetail from "./pages/LeaveDetail";
import { Approvals, Audit, History, NotFound } from "./pages/Lists";
import Login from "./pages/Login";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth />}>
        <Route index element={<Dashboard />} />
        <Route path="requests/:id" element={<LeaveDetail />} />
        <Route element={<RequireRole roles={["EMPLOYEE", "MANAGER"]} />}>
          <Route path="apply" element={<Apply />} />
          <Route path="requests" element={<History />} />
        </Route>
        <Route element={<RequireRole roles={["MANAGER", "HOD"]} />}>
          <Route path="approvals" element={<Approvals />} />
        </Route>
        <Route element={<RequireRole roles={["HOD"]} />}>
          <Route path="audit" element={<Audit />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
