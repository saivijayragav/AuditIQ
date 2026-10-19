import { useHealth } from "../../api/reference";
import "./TopBar.css";

export function TopBar() {
  const { data: health } = useHealth();
  const isHealthy = health?.status === "ok";

  return (
    <header className="topbar">
      <div className="topbar__left">
        {/* Breadcrumb area — populated by page-level context later */}
      </div>
      <div className="topbar__right">
        <div className="topbar__health" title={isHealthy ? "API connected" : "API offline"}>
          <span
            className={`topbar__dot ${isHealthy ? "topbar__dot--ok" : "topbar__dot--err"}`}
          />
          <span className="topbar__health-label">
            {isHealthy ? "Connected" : "Offline"}
          </span>
        </div>
      </div>
    </header>
  );
}
