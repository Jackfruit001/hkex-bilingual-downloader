import { useId, useState } from "react";
import { PencilIcon } from "./icons";

const FORBIDDEN = /[<>:"/\\|?*\u0000-\u001f]/g;
export const MAX_STEM = 110;

/** The name without `.pdf`, cleaned the way the server cleans it (SPEC §5): characters Windows
 *  does not allow and spaces become hyphens. The server still checks every name it receives. */
export function tidyStem(raw: string): string {
  const text = raw.replace(/\.pdf$/i, "").replace(FORBIDDEN, " ");
  return text
    .split(/\s+/)
    .filter(Boolean)
    .join("-")
    .replace(/-{2,}/g, "-")
    .replace(/^[-._ ]+|[-._ ]+$/g, "")
    .slice(0, MAX_STEM);
}

interface Props {
  suggested: string;
  value: string;
  onChange: (name: string | null) => void; // null puts the suggested name back
}

/** "Will be saved as" plus the name, with a pencil to change it. */
export function FilenameEditor({ suggested, value, onChange }: Props) {
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [problem, setProblem] = useState("");
  const edited = value !== suggested;

  const start = () => {
    setDraft(value.replace(/\.pdf$/i, ""));
    setProblem("");
    setEditing(true);
  };
  const save = () => {
    const stem = tidyStem(draft);
    if (!stem) return setProblem("Enter a name for the file.");
    onChange(`${stem}.pdf` === suggested ? null : `${stem}.pdf`);
    setEditing(false);
  };

  if (!editing) {
    return (
      <div className="file-row">
        <span className="file-label">Will be saved as</span>
        <div className="file-box">
          <span className="filename">{value}</span>
          <button type="button" className="icon-btn" onClick={start} aria-label="Edit filename" title="Edit filename">
            <PencilIcon />
          </button>
        </div>
        {edited && (
          <p className="file-note">
            Edited.{" "}
            <button type="button" className="link" onClick={() => onChange(null)}>
              Use the suggested name
            </button>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="file-row">
      <label className="file-label" htmlFor={id}>
        Edit filename
      </label>
      <div className="file-input">
        <input
          id={id}
          className="field"
          value={draft}
          maxLength={MAX_STEM}
          autoFocus
          onChange={(e) => {
            setDraft(e.target.value);
            setProblem("");
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              save();
            }
            if (e.key === "Escape") setEditing(false);
          }}
        />
        <span className="file-ext">.pdf</span>
      </div>
      {problem && (
        <p className="file-note text-danger" role="alert">
          {problem}
        </p>
      )}
      <p className="file-note">Spaces and characters that Windows doesn't allow become hyphens.</p>
      <div className="mt-2 flex gap-2">
        <button type="button" className="primary btn-sm" onClick={save}>
          Save name
        </button>
        <button type="button" className="secondary btn-sm" onClick={() => setEditing(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}
