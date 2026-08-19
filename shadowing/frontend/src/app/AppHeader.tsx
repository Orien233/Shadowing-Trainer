import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  BookOpenText,
  CaretDown,
  GearSix,
  Headphones,
  Question,
  Sparkle,
  Waveform,
  type Icon,
} from "@phosphor-icons/react";
import LanguageSelector from "../features/settings/LanguageSelector";
import { useLanguage } from "../i18n/LanguageContext";

export type AppPanel = "practice" | "wordLibrary" | "textGenerator" | "settings";
type PrimaryPanel = Exclude<AppPanel, "settings">;

interface NavItem {
  panel: PrimaryPanel;
  labelKey: string;
  icon: Icon;
}

const NAV_ITEMS: NavItem[] = [
  { panel: "practice", labelKey: "nav.practice", icon: Headphones },
  { panel: "wordLibrary", labelKey: "nav.wordLibrary", icon: BookOpenText },
  { panel: "textGenerator", labelKey: "nav.aiText", icon: Sparkle },
];

interface Props {
  activePanel: AppPanel;
  materialTitle: string | null;
  currentSentence: number | null;
  sentenceCount: number;
  onPanelChange: (panel: AppPanel) => void;
}

export default function AppHeader({
  activePanel,
  materialTitle,
  currentSentence,
  sentenceCount,
  onPanelChange,
}: Props) {
  const { t } = useLanguage();
  const [activePopover, setActivePopover] = useState<"language" | "help" | null>(null);
  const rootRef = useRef<HTMLElement | null>(null);
  const navRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const languageTriggerRef = useRef<HTMLButtonElement | null>(null);
  const helpTriggerRef = useRef<HTMLButtonElement | null>(null);
  const languagePopoverRef = useRef<HTMLDivElement | null>(null);
  const helpPopoverRef = useRef<HTMLDivElement | null>(null);
  const previousPopoverRef = useRef<typeof activePopover>(null);
  const restorePopoverFocusRef = useRef(true);

  function closePopover(restoreFocus: boolean) {
    restorePopoverFocusRef.current = restoreFocus;
    setActivePopover(null);
  }

  useEffect(() => {
    function closeFromOutside(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && !rootRef.current?.contains(target)) {
        closePopover(false);
      }
    }
    document.addEventListener("pointerdown", closeFromOutside);
    return () => document.removeEventListener("pointerdown", closeFromOutside);
  }, []);

  useEffect(() => {
    function closeOnEscape(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape" && activePopover) closePopover(true);
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [activePopover]);

  useEffect(() => {
    const previous = previousPopoverRef.current;
    if (activePopover) {
      const popover = activePopover === "language" ? languagePopoverRef.current : helpPopoverRef.current;
      const first = popover?.querySelector<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
      );
      (first ?? popover)?.focus();
    } else if (previous && restorePopoverFocusRef.current) {
      (previous === "language" ? languageTriggerRef : helpTriggerRef).current?.focus();
    }
    restorePopoverFocusRef.current = true;
    previousPopoverRef.current = activePopover;
  }, [activePopover]);

  function handleTabKeyDown(index: number, event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = (index + direction + NAV_ITEMS.length) % NAV_ITEMS.length;
    onPanelChange(NAV_ITEMS[nextIndex].panel);
    navRefs.current[nextIndex]?.focus();
  }

  return (
    <header className="product-header" ref={rootRef}>
      <div className="product-context">
        <div className="product-mark" aria-hidden="true">
          <Waveform size={22} weight="bold" />
        </div>
        <strong className="product-name">Shadowing</strong>
        <span className="context-divider" aria-hidden="true" />
        <div className="material-context">
          <span className="material-context-title" dir="auto">
            {materialTitle || t("nav.noMaterial")}
          </span>
          {sentenceCount > 0 && (
            <span className="material-context-meta">
              {currentSentence
                ? t("nav.sentencePosition", { current: currentSentence, total: sentenceCount })
                : t("nav.sentenceCount", { count: sentenceCount })}
            </span>
          )}
        </div>
      </div>

      <nav className="primary-tabs" role="tablist" aria-label={t("nav.primary")}>
        {NAV_ITEMS.map((item, index) => {
          const Icon = item.icon;
          const selected = activePanel === item.panel;
          return (
            <button
              key={item.panel}
              ref={(node) => { navRefs.current[index] = node; }}
              type="button"
              role="tab"
              id={`nav-${item.panel}`}
              aria-controls="workspace-panel"
              aria-selected={selected}
              tabIndex={selected || (activePanel === "settings" && index === 0) ? 0 : -1}
              className={`primary-tab ${selected ? "active" : ""}`}
              onClick={() => {
                closePopover(false);
                onPanelChange(item.panel);
              }}
              onKeyDown={(event) => handleTabKeyDown(index, event)}
            >
              <Icon size={18} weight={selected ? "fill" : "regular"} />
              <span>{t(item.labelKey)}</span>
            </button>
          );
        })}
      </nav>

      <div className="header-actions">
        <div className="header-popover-anchor">
          <button
            ref={languageTriggerRef}
            type="button"
            className={`header-control language-control ${activePopover === "language" ? "active" : ""}`}
            aria-expanded={activePopover === "language"}
            aria-haspopup="dialog"
            aria-controls="language-popover"
            onClick={() => {
              restorePopoverFocusRef.current = true;
              setActivePopover((current) => current === "language" ? null : "language");
            }}
          >
            <span>{t("nav.languageCompact")}</span>
            <CaretDown size={16} weight="bold" />
          </button>
          {activePopover === "language" && (
            <div ref={languagePopoverRef} id="language-popover" className="header-popover language-popover" role="dialog" aria-label={t("language.preferences")} tabIndex={-1}>
              <LanguageSelector />
            </div>
          )}
        </div>

        <div className="header-popover-anchor">
          <button
            ref={helpTriggerRef}
            type="button"
            className={`icon-button ${activePopover === "help" ? "active" : ""}`}
            aria-label={t("nav.help")}
            aria-expanded={activePopover === "help"}
            aria-haspopup="dialog"
            aria-controls="help-popover"
            onClick={() => {
              restorePopoverFocusRef.current = true;
              setActivePopover((current) => current === "help" ? null : "help");
            }}
          >
            <Question size={22} weight="regular" />
          </button>
          {activePopover === "help" && (
            <div ref={helpPopoverRef} id="help-popover" className="header-popover help-popover" role="dialog" aria-label={t("nav.help")} tabIndex={-1}>
              <strong>{t("nav.helpTitle")}</strong>
              <p>{t("app.workflow")}</p>
              <p className="muted">{t("app.securityNote")}</p>
            </div>
          )}
        </div>

        <button
          type="button"
          className={`icon-button ${activePanel === "settings" ? "active" : ""}`}
          aria-label={t("app.settings")}
          aria-pressed={activePanel === "settings"}
          onClick={() => {
            closePopover(false);
            onPanelChange("settings");
          }}
        >
          <GearSix size={22} weight={activePanel === "settings" ? "fill" : "regular"} />
        </button>
      </div>
    </header>
  );
}
