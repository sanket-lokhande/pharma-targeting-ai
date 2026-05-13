from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, TOP, BooleanVar, Button, Canvas, Checkbutton, Entry, Frame, Label, Scrollbar, Spinbox, StringVar, Tk, Toplevel, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import numpy as np
import pandas as pd

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

from app.schemas import MetricWeight
from app.services.analysis_engine import build_analysis_payload
from app.services.exporter import build_excel_output
from app.services.validation import validate_dataframe


class DesktopCopilotNLQApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Pharma Targeting - Copilot NLQ Desktop App")
        self.root.geometry("980x760")
        
        self.metric_columns: list[str] = []
        self.manual_weights: dict[str, float] = {}

        self.current_file_entry = self._build_file_selector("Current period file (.xlsx)", required=True)
        self.previous_file_entry = self._build_file_selector("Previous period file (.xlsx, optional)", required=False)
        self.output_file_entry = self._build_output_selector("Output workbook path (.xlsx, optional)")
        self.disease_market_entry = self._build_text_input("Disease Market (e.g., aGvHD, cGvHD, Hematology)", required=False)
        self.enable_live_research_var = BooleanVar(value=False)
        self._build_live_research_toggle()

        controls_frame = Frame(self.root)
        controls_frame.pack(fill="x", padx=12, pady=(14, 4))

        Label(controls_frame, text="Segmentation algorithm:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.algorithm_var = StringVar(value="kmeans")
        self.algorithm_combo = ttk.Combobox(
            controls_frame,
            textvariable=self.algorithm_var,
            values=["kmeans", "hierarchical", "rule_based"],
            state="readonly",
            width=18,
        )
        self.algorithm_combo.grid(row=0, column=1, sticky="w", padx=(0, 24), pady=4)

        Label(controls_frame, text="Number of clusters:").grid(row=0, column=2, sticky="w", padx=(0, 8), pady=4)
        self.n_clusters_var = StringVar(value="3")
        self.n_clusters_spin = Spinbox(
            controls_frame,
            from_=2,
            to=8,
            textvariable=self.n_clusters_var,
            width=6,
        )
        self.n_clusters_spin.grid(row=0, column=3, sticky="w", padx=(0, 24), pady=4)

        Label(controls_frame, text="Normalization:").grid(row=0, column=4, sticky="w", padx=(0, 8), pady=4)
        self.normalization_var = StringVar(value="minmax")
        self.normalization_combo = ttk.Combobox(
            controls_frame,
            textvariable=self.normalization_var,
            values=["minmax", "zscore"],
            state="readonly",
            width=12,
        )
        self.normalization_combo.grid(row=0, column=5, sticky="w", pady=4)

        button_frame = Frame(self.root)
        button_frame.pack(fill="x", padx=12, pady=10)

        Button(button_frame, text="Run Analysis", command=self.run_nlq_analysis).pack(side=LEFT)
        Button(button_frame, text="Copy Copilot Prompt", command=self.copy_copilot_prompt).pack(side=LEFT, padx=8)

        Label(self.root, text="Run Summary:").pack(anchor="w", padx=12, pady=(8, 4))
        self.summary_text = ScrolledText(self.root, height=18)
        self.summary_text.pack(fill=BOTH, expand=True, padx=12, pady=(0, 12))

    def _build_file_selector(self, label: str, required: bool) -> Entry:
        Label(self.root, text=label + (" *" if required else "")).pack(anchor="w", padx=12, pady=(10, 4))
        row = Frame(self.root)
        row.pack(fill="x", padx=12)

        entry = Entry(row)
        entry.pack(side=LEFT, fill="x", expand=True)

        Button(
            row,
            text="Browse",
            command=lambda: self._pick_file(entry),
        ).pack(side=RIGHT, padx=(8, 0))

        return entry

    def _build_output_selector(self, label: str) -> Entry:
        Label(self.root, text=label).pack(anchor="w", padx=12, pady=(10, 4))
        row = Frame(self.root)
        row.pack(fill="x", padx=12)

        entry = Entry(row)
        entry.pack(side=LEFT, fill="x", expand=True)

        Button(
            row,
            text="Browse",
            command=lambda: self._pick_output_file(entry),
        ).pack(side=RIGHT, padx=(8, 0))

        return entry

    def _build_text_input(self, label: str, required: bool = False) -> Entry:
        Label(self.root, text=label + (" *" if required else "")).pack(anchor="w", padx=12, pady=(8, 4))
        row = Frame(self.root)
        row.pack(fill="x", padx=12)

        entry = Entry(row)
        entry.pack(side=LEFT, fill="x", expand=True)
        return entry

    def _build_live_research_toggle(self) -> None:
        row = Frame(self.root)
        row.pack(fill="x", padx=12, pady=(6, 2))
        Checkbutton(
            row,
            text="Enable live internet research for market insights (requires internet)",
            variable=self.enable_live_research_var,
        ).pack(side=LEFT)

    def _pick_file(self, entry: Entry) -> None:
        selected = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if selected:
            entry.delete(0, END)
            entry.insert(0, selected)
            # If this is the current file, show weight assignment dialog
            if entry == self.current_file_entry:
                self._show_weight_dialog(selected)

    def _pick_output_file(self, entry: Entry) -> None:
        selected = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
        if selected:
            entry.delete(0, END)
            entry.insert(0, selected)

    def _show_weight_dialog(self, file_path: str) -> None:
        """Open a dialog to assign weights to each detected metric with scrollable area."""
        try:
            df = pd.read_excel(file_path, engine="openpyxl")
            _, metric_columns, _, _ = validate_dataframe(df)
            self.metric_columns = metric_columns
        except Exception as exc:
            messagebox.showerror("Error", f"Could not load metrics: {exc}")
            return

        dialog = Toplevel(self.root)
        dialog.title("Assign Metric Weights")
        dialog.geometry("800x700")
        dialog.transient(self.root)
        dialog.grab_set()

        # Header
        header_frame = Frame(dialog, bg="#4472C4", height=50)
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)

        header_label = Label(
            header_frame,
            text="Assign Weight for Each Metric (Total must equal 100)",
            font=("Arial", 12, "bold"),
            bg="#4472C4",
            fg="white",
        )
        header_label.pack(padx=12, pady=12, anchor="w")

        # Scrollable metrics frame
        canvas_frame = Frame(dialog)
        canvas_frame.pack(fill=BOTH, expand=True, padx=12, pady=12)

        canvas = Canvas(canvas_frame, bg="white", highlightthickness=0)
        scrollbar = Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = Frame(canvas, bg="white")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill="y")

        weight_entries: dict[str, Entry] = {}
        default_weight = round(100.0 / max(len(metric_columns), 1), 2)

        for metric in metric_columns:
            row = Frame(scrollable_frame, bg="white")
            row.pack(fill="x", pady=6, padx=4)

            label = Label(row, text=metric, width=45, anchor="w", bg="white", font=("Arial", 10))
            label.pack(side=LEFT, fill="x", expand=True, padx=(0, 8))

            entry = Entry(row, width=12, font=("Arial", 10), justify="center")
            entry.pack(side=LEFT, padx=4)
            entry.insert(0, str(default_weight))
            weight_entries[metric] = entry

        # Total indicator
        total_frame = Frame(dialog, bg="#E7E6E6", height=40)
        total_frame.pack(fill="x", padx=12, pady=(0, 12))
        total_frame.pack_propagate(False)

        total_label = Label(total_frame, text="Total: 0.00", font=("Arial", 11, "bold"), bg="#E7E6E6", fg="#333333")
        total_label.pack(padx=12, pady=8, anchor="e")

        def update_total() -> None:
            try:
                total = sum(float(entry.get() or 0) for entry in weight_entries.values())
                rounded_total = round(total, 2)
                total_label.config(text=f"Total: {rounded_total}")
                
                # Change color based on total
                if abs(rounded_total - 100.0) < 0.01:
                    total_label.config(fg="#0B7F1A")  # Green
                    total_frame.config(bg="#D4EDDA")
                else:
                    total_label.config(fg="#DC3545")  # Red
                    total_frame.config(bg="#F8D7DA")
            except ValueError:
                total_label.config(text="Total: (invalid)", fg="#DC3545")
                total_frame.config(bg="#F8D7DA")

        for entry in weight_entries.values():
            entry.bind("<KeyRelease>", lambda _: update_total())

        update_total()

        # Button frame
        button_frame = Frame(dialog, height=60)
        button_frame.pack(fill="x", padx=12, pady=12)
        button_frame.pack_propagate(False)

        apply_button = Button(
            button_frame,
            text="✓ Apply Weights",
            command=lambda: _validate_and_save(),
            font=("Arial", 11, "bold"),
            bg="#0B7F1A",
            fg="white",
            padx=20,
            pady=8,
        )
        apply_button.pack(side=LEFT, padx=6)

        cancel_button = Button(
            button_frame,
            text="✗ Cancel",
            command=dialog.destroy,
            font=("Arial", 11),
            bg="#DC3545",
            fg="white",
            padx=20,
            pady=8,
        )
        cancel_button.pack(side=LEFT, padx=6)

        def _validate_and_save() -> None:
            try:
                weights: dict[str, float] = {}
                for metric, entry in weight_entries.items():
                    weights[metric] = float(entry.get())

                total = round(sum(weights.values()), 4)
                if abs(total - 100.0) > 0.01:
                    messagebox.showerror(
                        "Invalid weights",
                        f"Total is {total:.2f}. Please adjust so the total equals 100.",
                    )
                    return

                self.manual_weights = weights
                dialog.destroy()
                messagebox.showinfo("Success", f"✓ Weights applied successfully!\n\nTotal: {total:.2f}")
            except ValueError:
                messagebox.showerror("Invalid input", "All weights must be valid numbers")

        # Mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def run_nlq_analysis(self) -> None:
        current_path_raw = self.current_file_entry.get().strip()
        if not current_path_raw:
            messagebox.showerror("Missing file", "Please choose a current period file.")
            return

        current_path = Path(current_path_raw)
        if not current_path.exists():
            messagebox.showerror("File not found", f"Current file not found: {current_path}")
            return

        try:
            current_raw = pd.read_excel(current_path, engine="openpyxl")
            id_column, metric_columns, validation_notes, current_df = validate_dataframe(current_raw)
        except Exception as exc:
            messagebox.showerror("Invalid file", f"Could not process current file:\n{exc}")
            return

        disease_market = self.disease_market_entry.get().strip()

        algorithm = (self.algorithm_var.get() or "kmeans").strip().lower()
        normalization = (self.normalization_var.get() or "minmax").strip().lower()
        try:
            n_clusters = int(self.n_clusters_var.get())
        except (TypeError, ValueError):
            messagebox.showerror("Invalid input", "Number of clusters must be an integer.")
            return
        if n_clusters < 2 or n_clusters > 8:
            messagebox.showerror("Invalid input", "Number of clusters must be between 2 and 8.")
            return

        previous_df = None
        previous_id_column = None

        previous_path_raw = self.previous_file_entry.get().strip()
        if previous_path_raw:
            previous_path = Path(previous_path_raw)
            if not previous_path.exists():
                messagebox.showerror("File not found", f"Previous file not found: {previous_path}")
                return

            try:
                previous_raw = pd.read_excel(previous_path, engine="openpyxl")
                previous_id_column, _, _, previous_df = validate_dataframe(previous_raw)
            except Exception as exc:
                messagebox.showerror("Invalid file", f"Could not process previous file:\n{exc}")
                return

        # Use manually assigned weights if available; otherwise distribute equally.
        # Zero-weight metrics are intentionally excluded.
        if self.manual_weights:
            selected_weights = {
                metric: weight for metric, weight in self.manual_weights.items() if float(weight) > 0
            }
            if not selected_weights:
                messagebox.showerror("Invalid weights", "Select at least one metric with weight greater than 0.")
                return
        else:
            if not metric_columns:
                messagebox.showerror("No metrics", "No numeric metrics were detected in the current file.")
                return
            equal_weight = round(100.0 / len(metric_columns), 4)
            selected_weights = {metric: equal_weight for metric in metric_columns}

        metric_weights = [
            MetricWeight(metric=metric, weight=weight)
            for metric, weight in selected_weights.items()
        ]

        try:
            payload = build_analysis_payload(
                current_df=current_df,
                id_column=id_column,
                metric_weights=metric_weights,
                normalization=normalization,
                segmentation_algorithm=algorithm,
                n_clusters=n_clusters,
                validation_notes=validation_notes,
                previous_df=previous_df,
                previous_id_column=previous_id_column,
                disease_market=disease_market,
                enable_live_research=self.enable_live_research_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("Analysis error", str(exc))
            return

        output_path = self._resolve_output_path()
        output_path.write_bytes(build_excel_output(payload))

        self._render_summary(
            output_path=output_path,
            payload=payload,
            final_weights=selected_weights,
            algorithm=algorithm,
            normalization=normalization,
            n_clusters=n_clusters,
            compare_previous=previous_df is not None,
        )
        if MATPLOTLIB_AVAILABLE:
            self._show_visual_dashboard(payload, [item.metric for item in metric_weights], disease_market)
        else:
            messagebox.showwarning(
                "Visuals unavailable",
                "Matplotlib is not installed in the current environment, so in-app charts were skipped.",
            )
        messagebox.showinfo("Success", f"Client-ready workbook created at:\n{output_path}")

    def _show_visual_dashboard(self, payload: dict, selected_metrics: list[str], disease_market: str) -> None:
        raw = payload.get("raw_with_scores", [])
        if not raw:
            return

        df = pd.DataFrame(raw)
        if df.empty or "decile" not in df.columns or "composite_score" not in df.columns:
            return

        dashboard = Toplevel(self.root)
        dashboard.title("Pharma Insights Dashboard")
        dashboard.geometry("1280x820")
        dashboard.configure(bg="#F3F5F9")

        title = f"Market Dashboard: {disease_market}" if disease_market else "Market Dashboard"
        header = Label(
            dashboard,
            text=title,
            font=("Segoe UI", 18, "bold"),
            bg="#F3F5F9",
            fg="#1D3557",
        )
        header.pack(anchor="w", padx=16, pady=(12, 2))

        subtitle = Label(
            dashboard,
            text="Lorenz curve, cluster map, and decile distribution from latest analysis",
            font=("Segoe UI", 10),
            bg="#F3F5F9",
            fg="#5C6B7A",
        )
        subtitle.pack(anchor="w", padx=16, pady=(0, 8))

        fig = Figure(figsize=(12.6, 7.6), dpi=100, facecolor="#F3F5F9")
        ax_lorenz = fig.add_subplot(2, 2, 1)
        ax_bubble = fig.add_subplot(2, 2, 2)
        ax_decile = fig.add_subplot(2, 1, 2)

        self._plot_lorenz_curve(ax_lorenz, df)
        self._plot_cluster_bubble(ax_bubble, df, selected_metrics)
        self._plot_decile_bar(ax_decile, df)

        fig.tight_layout(pad=2.4)
        canvas = FigureCanvasTkAgg(fig, master=dashboard)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=BOTH, expand=True, padx=10, pady=8)

    def _plot_lorenz_curve(self, ax, df: pd.DataFrame) -> None:
        work = df[["decile", "composite_score"]].copy()
        work["decile_num"] = work["decile"].astype(str).str.replace("D", "", regex=False).astype(int)

        grouped = (
            work.groupby("decile_num", as_index=False)
            .agg(prescribers=("composite_score", "count"), potential=("composite_score", "sum"))
            .sort_values("decile_num", ascending=False)
        )

        grouped["cum_prescribers"] = grouped["prescribers"].cumsum()
        grouped["cum_potential"] = grouped["potential"].cumsum()

        total_prescribers = grouped["prescribers"].sum() or 1
        total_potential = grouped["potential"].sum() or 1

        x = (grouped["cum_potential"] / total_potential) * 100
        y = (grouped["cum_prescribers"] / total_prescribers) * 100

        x = pd.concat([pd.Series([0.0]), x], ignore_index=True)
        y = pd.concat([pd.Series([0.0]), y], ignore_index=True)

        ax.plot(x, y, marker="o", linewidth=2.6, color="#2A6FBA")
        ax.plot([0, 100], [0, 100], linestyle="--", linewidth=1.2, color="#A0A7B4")
        ax.fill_between(x, y, alpha=0.15, color="#2A6FBA")
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.set_title("Lorenz Curve for HCPs", fontsize=12, fontweight="bold", color="#1D3557")
        ax.set_xlabel("Cumulative % of Potential")
        ax.set_ylabel("Cumulative % of Prescribers")
        ax.grid(alpha=0.3)
        ax.set_facecolor("#FFFFFF")

    def _plot_cluster_bubble(self, ax, df: pd.DataFrame, selected_metrics: list[str]) -> None:
        axis_metrics = [m for m in selected_metrics if m in df.columns][:2]
        if len(axis_metrics) < 2:
            axis_metrics = ["composite_score", "decile_numeric"] if "decile_numeric" in df.columns else ["composite_score", "composite_score"]

        x_col, y_col = axis_metrics[0], axis_metrics[1]
        labels = df["segment_label"].fillna("Segment") if "segment_label" in df.columns else pd.Series(["Segment"] * len(df))
        unique_labels = sorted(labels.unique())

        comp = df["composite_score"].astype(float)
        comp_min, comp_max = float(comp.min()), float(comp.max())
        if comp_max - comp_min <= 1e-9:
            sizes = np.full(len(df), 90.0)
        else:
            sizes = 60 + 340 * ((comp - comp_min) / (comp_max - comp_min))

        palette = ["#2A6FBA", "#EF476F", "#06D6A0", "#8D6CAB", "#F4A261", "#118AB2", "#8338EC"]
        for idx, label in enumerate(unique_labels):
            mask = labels == label
            ax.scatter(
                df.loc[mask, x_col],
                df.loc[mask, y_col],
                s=sizes[mask.values],
                alpha=0.65,
                color=palette[idx % len(palette)],
                edgecolors="#2F3B52",
                linewidths=0.4,
                label=str(label),
            )

        ax.set_title("Cluster Bubble View", fontsize=12, fontweight="bold", color="#1D3557")
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.grid(alpha=0.25)
        ax.legend(loc="best", fontsize=8, frameon=False)
        ax.set_facecolor("#FFFFFF")

    def _plot_decile_bar(self, ax, df: pd.DataFrame) -> None:
        counts = (
            df["decile"].astype(str).str.replace("D", "", regex=False).astype(int)
            .value_counts()
            .sort_index(ascending=False)
        )
        deciles = [f"D{d}" for d in counts.index.tolist()]
        vals = counts.values.tolist()

        bars = ax.bar(deciles, vals, color="#457B9D", edgecolor="#2F3B52", linewidth=0.6)
        ax.set_title("HCP Count by Decile", fontsize=12, fontweight="bold", color="#1D3557")
        ax.set_xlabel("Decile")
        ax.set_ylabel("Number of HCPs")
        ax.grid(axis="y", alpha=0.25)
        ax.set_facecolor("#FFFFFF")

        for bar, value in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (max(vals) * 0.01 if vals else 0),
                str(value),
                ha="center",
                va="bottom",
                fontsize=8,
                color="#1D3557",
            )

    def _resolve_output_path(self) -> Path:
        output_raw = self.output_file_entry.get().strip()
        if output_raw:
            return Path(output_raw)
        return Path.cwd() / f"client_ready_targeting_nlq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    def _render_summary(
        self,
        output_path: Path,
        payload: dict,
        final_weights: dict[str, float],
        algorithm: str,
        normalization: str,
        n_clusters: int,
        compare_previous: bool,
    ) -> None:
        self.summary_text.delete("1.0", END)

        final_metrics = list(final_weights.keys())

        summary_lines = [
            "Analysis completed successfully.",
            f"Output: {output_path}",
            f"Metrics: {final_metrics}",
            f"Weights: {final_weights}",
            f"Normalization: {normalization}",
            f"Segmentation algorithm: {algorithm}",
            f"Cluster count: {n_clusters}",
            f"Comparison performed: {compare_previous}",
            f"Disease market: {self.disease_market_entry.get().strip() or 'Not specified'}",
            f"Live internet research: {'Enabled' if self.enable_live_research_var.get() else 'Disabled'}",
            "",
            "Summary insights:",
        ]

        for item in payload.get("summary_insights", []):
            summary_lines.append(f"- {item}")

        self.summary_text.insert(END, "\n".join(summary_lines))

    def copy_copilot_prompt(self) -> None:
        summary = self.summary_text.get("1.0", END).strip()
        if not summary:
            messagebox.showwarning("No summary", "Run analysis first to generate a summary prompt.")
            return

        prompt = (
            "Use this local NLQ deciling and segmentation summary and help me create an executive email:\n\n"
            + summary
        )

        self.root.clipboard_clear()
        self.root.clipboard_append(prompt)
        self.root.update()
        messagebox.showinfo("Copied", "Copilot prompt copied to clipboard.")


def main() -> None:
    root = Tk()
    app = DesktopCopilotNLQApp(root)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    main()
