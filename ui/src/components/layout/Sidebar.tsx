import { NavLink, useParams } from "react-router-dom";
import {
  LayoutDashboard,
  Upload,
  Table2,
  GitBranch,
  FileText,
  ClipboardCheck,
  Scale,
  GitCompare,
  AlertCircle,
  Plus,
  Shield,
} from "lucide-react";
import { ROUTES } from "../../utils/constants";
import "./Sidebar.css";

const NAV_ITEMS = [
  { label: "Dashboard", path: ROUTES.dashboard, icon: LayoutDashboard },
];

const ENGAGEMENT_NAV = [
  { label: "Overview", path: ROUTES.engagement, icon: LayoutDashboard },
  { label: "Ingest TB", path: ROUTES.ingestTb, icon: Upload },
  { label: "TB Lines", path: ROUTES.tbLines, icon: Table2 },
  { label: "Map FSLIs", path: ROUTES.mapping, icon: GitBranch },
  { label: "Ingest FS", path: ROUTES.ingestFs, icon: FileText },
  { label: "FS Review", path: ROUTES.fsReview, icon: ClipboardCheck },
  { label: "Materiality", path: ROUTES.materiality, icon: Scale },
  { label: "Reconcile", path: ROUTES.recon, icon: GitCompare },
  { label: "Exceptions", path: ROUTES.exceptions, icon: AlertCircle },
];

export function Sidebar() {
  const { id } = useParams<{ id: string }>();

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <Shield size={22} className="sidebar__logo" />
        <span className="sidebar__brand-text">AuditIQ</span>
      </div>

      <nav className="sidebar__nav">
        <div className="sidebar__section">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end
              className={({ isActive }) =>
                `sidebar__link ${isActive ? "sidebar__link--active" : ""}`
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
          <NavLink
            to={ROUTES.newEngagement}
            className={({ isActive }) =>
              `sidebar__link ${isActive ? "sidebar__link--active" : ""}`
            }
          >
            <Plus size={18} />
            New Engagement
          </NavLink>
        </div>

        {id && (
          <div className="sidebar__section">
            <div className="sidebar__section-title">Engagement #{id}</div>
            {ENGAGEMENT_NAV.map((item) => (
              <NavLink
                key={item.label}
                to={item.path(id)}
                end={item.label === "Overview"}
                className={({ isActive }) =>
                  `sidebar__link ${isActive ? "sidebar__link--active" : ""}`
                }
              >
                <item.icon size={18} />
                {item.label}
              </NavLink>
            ))}
          </div>
        )}
      </nav>

      <div className="sidebar__footer">
        <span className="sidebar__version">v0.1.0</span>
      </div>
    </aside>
  );
}
