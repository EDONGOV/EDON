import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const toolOp = (tool: unknown) => {
  if (!tool) return "N/A";
  if (typeof tool === "string") return tool;
  if (typeof tool === "object") {
    const candidate = tool as { op?: unknown; name?: unknown };
    const name = typeof candidate.name === "string" ? candidate.name : "";
    const op = typeof candidate.op === "string" ? candidate.op : "";
    if (name && op) return `${name}.${op}`;
    if (op) return op;
    if (name) return name;
  }
  return "N/A";
};
