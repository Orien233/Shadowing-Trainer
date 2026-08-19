import { useEffect, useRef } from "react";
import { Books, X } from "@phosphor-icons/react";
import type { Material } from "../../types";
import { useLanguage } from "../../i18n/LanguageContext";
import MaterialList from "./MaterialList";
import MaterialUploader from "./MaterialUploader";

interface Props {
  open: boolean;
  materials: Material[];
  activeId: number | null;
  onOpenChange: (open: boolean) => void;
  onUploaded: (material: Material) => void;
  onSelect: (id: number) => void;
  onProcessed: (material: Material) => void;
  onDeleted: (materialId: number) => void;
}

export default function MaterialDrawer({
  open,
  materials,
  activeId,
  onOpenChange,
  onUploaded,
  onSelect,
  onProcessed,
  onDeleted,
}: Props) {
  const { t } = useLanguage();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const wasOpenRef = useRef(false);

  useEffect(() => {
    if (open) {
      wasOpenRef.current = true;
      closeRef.current?.focus();
      return;
    }
    if (wasOpenRef.current) {
      triggerRef.current?.focus();
      wasOpenRef.current = false;
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onOpenChange(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onOpenChange, open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="material-rail-trigger"
        aria-label={t("material.openDrawer")}
        aria-expanded={open}
        aria-controls="material-drawer"
        onClick={() => onOpenChange(true)}
      >
        <Books size={20} weight="regular" />
        <span>{t("material.drawerRail")}</span>
        <strong>{materials.length}</strong>
      </button>

      {open && (
        <>
          <button
            type="button"
            className="drawer-backdrop"
            tabIndex={-1}
            aria-label={t("material.dismissDrawer")}
            onClick={() => onOpenChange(false)}
          />
          <aside
            id="material-drawer"
            className="material-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={t("material.drawerTitle")}
          >
            <div className="material-drawer-header">
              <div>
                <span className="eyebrow">{t("material.workspace")}</span>
                <h2>{t("material.drawerTitle")}</h2>
              </div>
              <button
                ref={closeRef}
                type="button"
                className="icon-button"
                aria-label={t("material.closeDrawer")}
                onClick={() => onOpenChange(false)}
              >
                <X size={20} weight="bold" />
              </button>
            </div>
            <div className="material-drawer-body">
              <MaterialUploader onUploaded={(material) => {
                onUploaded(material);
                onOpenChange(false);
              }} />
              <MaterialList
                materials={materials}
                activeId={activeId}
                onSelect={(id) => {
                  onSelect(id);
                  onOpenChange(false);
                }}
                onProcessed={onProcessed}
                onDeleted={onDeleted}
              />
            </div>
          </aside>
        </>
      )}
    </>
  );
}
