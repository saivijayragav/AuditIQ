import { useCallback, useState, useRef, type DragEvent } from "react";
import { Upload } from "lucide-react";
import "./DropZone.css";

interface DropZoneProps {
  accept?: string;
  label?: string;
  onFile: (file: File) => void;
  disabled?: boolean;
}

export function DropZone({
  accept = ".xlsx,.xls,.csv,.pdf",
  label = "Drag & drop a file here, or click to browse",
  onFile,
  disabled = false,
}: DropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrag = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDragIn = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.items?.length) setDragging(true);
  }, []);

  const handleDragOut = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      if (disabled) return;
      const file = e.dataTransfer.files?.[0];
      if (file) onFile(file);
    },
    [onFile, disabled]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onFile(file);
      // Reset so same file can be re-selected
      e.target.value = "";
    },
    [onFile]
  );

  return (
    <div
      className={`dropzone ${dragging ? "dropzone--active" : ""} ${disabled ? "dropzone--disabled" : ""}`}
      onDragEnter={handleDragIn}
      onDragLeave={handleDragOut}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
    >
      <Upload size={32} className="dropzone__icon" />
      <p className="dropzone__label">{label}</p>
      <p className="dropzone__hint">Accepted: {accept}</p>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleChange}
        className="visually-hidden"
        disabled={disabled}
      />
    </div>
  );
}
