import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LanguageProvider } from "../../i18n/LanguageContext";
import MaterialDrawer from "./MaterialDrawer";

vi.mock("./MaterialUploader", () => ({ default: () => <div>Uploader</div> }));
vi.mock("./MaterialList", () => ({ default: () => <div>Material list</div> }));

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <LanguageProvider>
      <MaterialDrawer
        open={open}
        materials={[]}
        activeId={null}
        onOpenChange={setOpen}
        onUploaded={() => undefined}
        onSelect={() => undefined}
        onProcessed={() => undefined}
        onDeleted={() => undefined}
      />
    </LanguageProvider>
  );
}

describe("MaterialDrawer", () => {
  it("moves focus into the drawer and returns it to the trigger", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open material library" });
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Material library" });
    expect(dialog).toBeInTheDocument();
    const close = within(dialog).getByRole("button", { name: "Close material library" });
    expect(close).toHaveFocus();

    fireEvent.click(close);
    expect(screen.queryByRole("dialog", { name: "Material library" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("closes with Escape", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open material library" });
    fireEvent.click(trigger);
    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByRole("dialog", { name: "Material library" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
