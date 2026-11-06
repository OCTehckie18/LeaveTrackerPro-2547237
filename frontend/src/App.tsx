import { Route, Routes } from "react-router-dom";
import { RequireAuth } from "./components/Layout";
import { useMe } from "./lib/auth";
import Login from "./pages/Login";

function Home() {
  const me = useMe();
  return (
    <div className="card p-6">
      <h1 className="text-xl font-semibold">Welcome, {me.user.name}</h1>
      <p className="mt-1 text-sm text-muted">The dashboard arrives with the employee screens.</p>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth />}>
        <Route index element={<Home />} />
      </Route>
    </Routes>
  );
}
