import { NavLink, Outlet, useLocation, Navigate } from "react-router-dom";
import { useAuth } from "../../auth";
import { Brand } from "../../components/Brand";

const NAV: [string, [string, string][]][] = [
  ["Doctor", [["/admin/doctor", "Examinations"], ["/admin/external", "External systems"]]],
  ["Lab", [["/admin/experiments", "Experiments"], ["/admin/playground", "Playground"], ["/admin/configurations", "Configurations"]]],
  ["Library", [["/admin/documents", "Documents"], ["/admin/questions", "Question set"]]],
];

export default function AdminLayout() {
  const { user, loading, signOut } = useAuth();
  const location = useLocation();
  if (loading) return null;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  if (user.role !== "admin")
    return (
      <div className="login-page">
        <div className="panel pad stack">
          <h1>Admins only</h1>
          <p className="muted">You are signed in as {user.email}, which has no admin role.</p>
        </div>
      </div>
    );
  return (
    <div className="admin">
      <aside className="sidebar">
        <Brand to="/admin/doctor" />
        <nav>
          {NAV.map(([group, links]) => (
            <div key={group} className="nav-group">
              <span className="nav-title">{group}</span>
              {links.map(([to, label]) => (
                <NavLink key={to} to={to} className="nav-link">
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <NavLink to="/" className="nav-link">
            Open the chat
          </NavLink>
          <span className="faint">{user.email}</span>
          <button className="quiet small" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  );
}
