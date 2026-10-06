import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...werte: ClassValue[]) {
  return twMerge(clsx(werte));
}
