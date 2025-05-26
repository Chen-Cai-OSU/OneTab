#!/usr/bin/env python3
"""
OneTab Manager - A tool to search, filter, and batch delete OneTab saved tabs
"""
from urllib.parse import urlparse, urlunparse
import tkinter as tk
import re
import requests
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re
from urllib.parse import unquote, urlparse, parse_qs
import json
import os
from collections import Counter
from urllib.parse import quote
from tkinter import filedialog
import subprocess

ONE_TAB_PREFIX = "chrome-extension://lnepcdnpflggegdhpnnffojfdpfoambo" "/suspended.html"


class OneTabManager:
    def __init__(self, root):
        self.root = root
        self.current_filepath = None
        self.root.title("OneTab Manager")
        self.root.geometry("1200x700")

        self.tabs_data = []
        self.filtered_data = []

        self.setup_ui()

    def fetch_arxiv_title(self, arxiv_id: str) -> str | None:
        """Call arXiv’s API and return the paper’s title (or None on failure)."""
        ARXIV_API = "http://export.arxiv.org/api/query?id_list={id}"
        url = ARXIV_API.format(id=arxiv_id)
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            # arXiv’s Atom feed uses the Atom namespace
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entry = root.find("atom:entry", ns)
            if entry is not None:
                title_elem = entry.find("atom:title", ns)
                if title_elem is not None and title_elem.text:
                    # Collapse any internal whitespace/newlines
                    return " ".join(title_elem.text.split())
        except Exception:
            pass
        return None

    def setup_ui(self):
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # File operations frame
        file_frame = ttk.LabelFrame(main_frame, text="File Operations", padding="5")
        file_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ttk.Button(file_frame, text="Load OneTab Data", command=self.load_file).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            file_frame, text="Save Filtered Data", command=self.save_filtered
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_frame, text="Export as JSON", command=self.export_json).pack(
            side=tk.LEFT, padx=5
        )
        btn = ttk.Button(file_frame, text="Save Current", command=self.save_current)
        btn.pack(side="left", padx=4, pady=4)

        # Search and filter frame
        search_frame = ttk.LabelFrame(main_frame, text="Search & Filter", padding="5")
        search_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(
            search_frame, textvariable=self.search_var, width=40
        )
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind("<KeyRelease>", self.on_search_changed)

        ttk.Button(search_frame, text="Clear Search", command=self.clear_search).pack(
            side=tk.LEFT, padx=5
        )

        # Selection operations
        ttk.Button(
            search_frame, text="Select All Visible", command=self.select_all_visible
        ).pack(side=tk.LEFT, padx=20)
        ttk.Button(search_frame, text="Deselect All", command=self.deselect_all).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            search_frame, text="Delete Selected", command=self.delete_selected
        ).pack(side=tk.LEFT, padx=5)

        # Status label
        self.status_label = ttk.Label(search_frame, text="No data loaded")
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # Create treeview with scrollbars
        tree_frame = ttk.Frame(main_frame)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)

        # Treeview
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("title", "uRL", "domain"),
            show="tree headings",
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set,
            selectmode="extended",
        )

        # define each heading…
        self.tree.heading(
            "title", text="Title", command=lambda: self.sort_by("title", False)
        )
        # self.tree.heading("url", text="Url", command=lambda: self.sort_by("url", False))
        self.tree.heading(
            "domain", text="Domain", command=lambda: self.sort_by("domain", False)
        )

        # Configure scrollbars
        v_scrollbar.config(command=self.tree.yview)
        h_scrollbar.config(command=self.tree.xview)

        # Grid layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")

        # Configure columns
        self.tree.column("#0", width=50, stretch=False)
        self.tree.column("title", width=400)
        self.tree.column("uRL", width=500)
        self.tree.column("domain", width=200)

        # Configure headings
        self.tree.heading("#0", text="#")
        self.tree.heading("title", text="Title")
        self.tree.heading("uRL", text="URL")
        self.tree.heading("domain", text="Domain")

        # Style configuration for better visibility
        style = ttk.Style()
        style.configure(
            "Treeview", selectbackground="lightblue", selectforeground="black"
        )

        # Bind selection change event
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_info())
        self.tree.bind("<Double-1>", self.on_double_click)

        # Add keyboard shortcuts
        self.root.bind("<Control-a>", lambda e: self.select_all_visible())
        self.root.bind("<Control-A>", lambda e: self.select_all_visible())
        self.root.bind("<Delete>", lambda e: self.delete_selected())
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus())
        self.root.bind("<Control-F>", lambda e: self.search_entry.focus())

        # Info frame
        info_frame = ttk.Frame(main_frame)
        info_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        self.info_label = ttk.Label(
            info_frame, text="Total: 0 tabs | Filtered: 0 tabs | Selected: 0 tabs"
        )
        self.info_label.pack(side=tk.LEFT)

        # Keyboard shortcuts info
        shortcuts_label = ttk.Label(
            info_frame,
            text="Shortcuts: Ctrl+A (Select All) | Delete (Delete Selected) | Ctrl+F (Search)",
            foreground="gray",
        )
        shortcuts_label.pack(side=tk.RIGHT, padx=10)

        # after you create & layout everything, before root.mainloop()
        self.root.update()  # make sure window exists
        self.root.lift()    # lift it above all other windows
        # temporarily make it the top‐most window
        self.root.attributes('-topmost', True)
        # then turn topmost off so the user can switch away
        self.root.after_idle(self.root.attributes, '-topmost', False)
        # finally, give it keyboard focus
        self.root.focus_force()

    def on_double_click(self, event):
        """Open the clicked tab in Chrome and remove it from the list."""
        # figure out which row was clicked
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        # columns = (title, url, domain), so value[1] is the URL
        title, url, domain = self.tree.item(item_id, "values")
        if not url:
            messagebox.showinfo("No URL", "There’s no URL in this row.")
            return

        # open in Chrome (macOS)
        try:
            subprocess.Popen(["open", "-a", "Google Chrome", url])
        except Exception:
            # fallback to default browser
            import webbrowser
            webbrowser.open_new_tab(url)

        # remove from in-memory lists
        # find its index in the filtered list
        idx = int(self.tree.item(item_id, "text")) - 1
        tab = self.filtered_data.pop(idx)
        # also remove from the master list
        if tab in self.tabs_data:
            self.tabs_data.remove(tab)

        # refresh the display (will re-populate the tree and update counts)
        self.refresh_display()

    def sort_by(self, col, reverse=False):
        """
        Sort self.tabs_data by given column (e.g. 'domain', 'title', 'url'),
        then repopulate the Treeview in that order.
        """
        # sort the in-memory list
        self.tabs_data.sort(key=lambda e: e.get(col) or "", reverse=reverse)

        # clear existing rows
        for row in self.tree.get_children():
            self.tree.delete(row)

        # re-insert rows in new order
        for entry in self.tabs_data:
            self.tree.insert(
                "", 
                "end", 
                values=(entry.get("title"), entry.get("url"), entry.get("domain"))
            )

        # next time we click, flip the sort order
        # store the new reverse flag on the heading
        self.tree.heading(col, command=lambda: self.sort_by(col, not reverse))

    def print_domain_stats(self, top_n=30):
        """
        Count domains in self.tabs_data, then print the top `top_n`
        along with their absolute counts and percentage of the total.
        """
        # collect only non-empty domains
        domains = [e.get("domain") for e in self.tabs_data if e.get("domain")]
        total = len(domains)
        if total == 0:
            print("No domains to analyze.")
            return

        counts = Counter(domains)
        most = counts.most_common(top_n)

        # sum up just the top_n counts
        top_total = sum(cnt for _, cnt in most)
        top_pct = top_total / total * 100

        # header
        print(f"Total entries with domains: {total}\n")
        print(f"Top {len(most)} domains by frequency:")
        for rank, (domain, cnt) in enumerate(most, start=1):
            pct = cnt / total * 100
            print(f"{rank:2}. {domain:<30} {cnt:5d} entries   ({pct:5.2f}%)")

        # aggregated summary
        print("\n" + "-" * 60)
        print(
            f"Combined count for top {len(most)} domains: "
            f"{top_total} entries ({top_pct:.2f}% of total)"
        )

    def parse_onetab_line(self, line):
        """Parse a OneTab export line to extract title and URL"""
        line = line.strip()
        if not line:
            return None

        # 0) plain URL case. Commented out temporarily for faster development.
        # if "arxiv.org/" in line:
        #     url = line
        #     title = line

        #     # is it an arXiv PDF URL?
        #     m = re.search(r"arxiv\.org/(?:pdf|abs)/([0-9\.v]+)", url)
        #     if m:
        #         arxiv_id = m.group(1)
        #         real_title = self.fetch_arxiv_title(arxiv_id)
        #         if real_title:
        #             print(f"Fetched arXiv title for {arxiv_id!r}: {real_title!r}")
        #             title = real_title

        #     return {"title": title, "url": url}

        # 1) chrome-extension://...#ttl=…&uri=… (OneTab export)
        if line.startswith("chrome-extension://"):
            try:
                parsed = urlparse(line)
                # parse both query and fragment
                params = parse_qs(parsed.query)
                params.update(parse_qs(parsed.fragment))

                # OneTab sometimes uses 'ttl' instead of 'title', and 'uri' instead of 'url'
                raw_title = (params.get("title") or params.get("ttl") or [""])[0]
                raw_url = (params.get("url") or params.get("uri") or [""])[0]

                title = unquote(raw_title)
                url = unquote(raw_url)

                if title and url:
                    return {"title": title, "url": url}
            except Exception:
                # silently fall through to other formats
                pass

        # 2) URL | Title
        if " | " in line:
            url_part, title_part = line.split(" | ", 1)
            return {"title": title_part.strip(), "url": url_part.strip()}

        # 3) bare URL (http[s] or file)
        if re.match(r"^(https?|file)://", line):
            return {"title": line, "url": line}

        # 5) fallback: treat as a section header or unlabeled entry
        return {"title": line, "url": None}

    def _remove_fragment(self, url: str) -> str:
        """
        Strip off any “#…” fragment from the given URL.
        """
        return url
        # parsed = urlparse(url)
        # # rebuild the URL with an empty fragment
        # return urlunparse(parsed._replace(fragment=""))

    def dedupe_tabs(self, tabs):
        """Return a new list of tabs, keeping only the first occurrence of each title."""
        seen = set()
        unique_tabs = []
        for tab in tabs:
            title = tab.get("title")
            # Skip if title is missing or already seen
            if not title or title in seen:
                continue
            seen.add(title)
            unique_tabs.append(tab)
        print(f"Removed {len(tabs) - len(unique_tabs)} duplicate tab(s).")
        return unique_tabs

    def dedupe_urls(self, entries):
        """
        Remove any entries with duplicate URLs, keeping only the most
        recent occurrence, and print how many were dropped.
        """
        seen_urls = set()
        deduped_rev = []
        duplicates = 0

        # iterate backwards so that the *last* (i.e. most recent) wins
        for entry in reversed(entries):
            url = entry.get('url')
            # remove fragment identifiers
            cleaned_url = self._remove_fragment(url) if url else None
            if url and cleaned_url in seen_urls:
                duplicates += 1
                continue
            if url:
                seen_urls.add(cleaned_url)
            deduped_rev.append(entry)

        deduped = list(reversed(deduped_rev))
        print(f"Removed {duplicates} duplicate url(s).")
        return deduped

    def _parse_onetab_line(self, line):
        """Parse a OneTab export line to extract title and URL"""
        line = line.strip()
        if not line:
            return None

        # Check if it's a chrome-extension URL
        if line.startswith("chrome-extension://"):
            try:
                # Parse the URL parameters
                parsed = urlparse(line)
                params = parse_qs(parsed.query)

                title = unquote(params.get("title", [""])[0])
                url = unquote(params.get("url", [""])[0])

                if title and url:
                    return {"title": title, "url": url}
            except:
                pass

        # Try to parse as "URL | Title" format
        elif " | " in line:
            parts = line.split(" | ", 1)
            if len(parts) == 2:
                return {"title": parts[1], "url": parts[0]}

        # Try to parse as just URL
        elif line.startswith("http"):
            return {"title": line, "url": line}

        else:
            # treat it as a header/label
            return {"title": line, "url": None}

    def get_domain(self, url):
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc or "Unknown"
        except:
            return "Unknown"

    def load_file(self):
        """Load OneTab data from file"""
        filename = filedialog.askopenfilename(
            title="Select OneTab Export File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )

        # remember it for future saves
        self.current_filepath = filename

        if not filename:
            return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self.tabs_data = []
            for line in lines:
                tab = self.parse_onetab_line(line)
                if tab:
                    tab["domain"] = self.get_domain(tab["url"])
                    self.tabs_data.append(tab)
                else:
                    # If line is not a valid tab, treat it as a header/label
                    self.tabs_data.append(
                        {"title": line.strip(), "url": None, "domain": "Unknown"}
                    )
            self.tabs_data = self.dedupe_urls(self.tabs_data)
            self.tabs_data = self.dedupe_tabs(self.tabs_data)
            self.print_domain_stats(top_n=30)
            self.filtered_data = self.tabs_data.copy()
            self.refresh_display()
            self.status_label.config(text=f"Loaded {len(self.tabs_data)} tabs")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file: {str(e)}")

        print(f"Read {len(lines)} lines, parsed {len(self.tabs_data)} tabs")

    def save_current(self):
        """
        Write out self.tabs_data in OneTab format,
        auto‐naming the file with an increasing _vN suffix.
        """
        if self.current_filepath:
            dirpath, fn = os.path.split(self.current_filepath)
            name, ext = os.path.splitext(fn)

            # if name ends in "_vN", strip it off to find the base
            m = re.match(r"^(.*)_v(\d+)$", name)
            base = m.group(1) if m else name

            # scan dir for existing versions of base
            pat = re.compile(rf"^{re.escape(base)}_v(\d+){re.escape(ext)}$")
            maxv = 0
            for f in os.listdir(dirpath):
                mm = pat.match(f)
                if mm:
                    v = int(mm.group(1))
                    if v > maxv:
                        maxv = v

            newv = maxv + 1
            save_name = f"{base}_v{newv}{ext}"
            path = os.path.join(dirpath, save_name)
        else:
            # fallback if no file was loaded
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files","*.txt"),("All files","*.*")],
            )
            if not path:
                return

        # now build the OneTab lines
        lines = []
        for entry in self.tabs_data:
            url   = entry.get("url")
            title = entry.get("title","")
            # if url:
            #     frag = f"ttl={quote(title)}&uri={quote(url)}"
            #     lines.append(f"{ONE_TAB_PREFIX}#{frag}")
            # else:
            # breakpoint()
            lines.append(f"{url} | {title}")

        # write it out
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # remember this file for next time
        self.current_filepath = path
        print(f"Saved {len(lines)} tabs to {path!r}")

    def refresh_display(self):
        """Refresh the treeview display"""
        # Save current selection
        selected_indices = set()
        for item in self.tree.selection():
            idx = int(self.tree.item(item)["text"]) - 1
            if 0 <= idx < len(self.filtered_data):
                tab = self.filtered_data[idx]
                selected_indices.add(self.tabs_data.index(tab))

        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Add filtered items
        items_to_select = []
        for i, tab in enumerate(self.filtered_data):
            original_index = self.tabs_data.index(tab)
            item = self.tree.insert(
                "",
                "end",
                text=f"{i+1}",
                values=(tab["title"], tab["url"], tab["domain"]),
            )
            if original_index in selected_indices:
                items_to_select.append(item)

        # Restore selection
        if items_to_select:
            self.tree.selection_set(items_to_select)

        # Update info
        self.update_info()

    def update_info(self):
        """Update the info label"""
        total = len(self.tabs_data)
        filtered = len(self.filtered_data)
        selected = len(self.tree.selection())
        self.info_label.config(
            text=f"Total: {total} tabs | Filtered: {filtered} tabs | Selected: {selected} tabs"
        )

    def on_search_changed(self, event=None):
        """Handle search text change"""
        search_text = self.search_var.get().lower()

        if not search_text:
            self.filtered_data = self.tabs_data.copy()
        else:
            self.filtered_data = []
            for tab in self.tabs_data:
                title = (tab.get("title") or "").lower()
                url   = (tab.get("url")   or "").lower()
                if search_text in title or search_text in url:
                    self.filtered_data.append(tab)

        self.refresh_display()

    def clear_search(self):
        """Clear search and show all tabs"""
        self.search_var.set("")
        self.on_search_changed()

    def select_all_visible(self):
        """Select all currently visible (filtered) tabs"""
        all_items = self.tree.get_children()
        if all_items:
            self.tree.selection_set(all_items)
        self.update_info()

    def deselect_all(self):
        """Deselect all tabs"""
        self.tree.selection_remove(self.tree.get_children())
        self.update_info()

    def delete_selected(self):
        """Delete selected tabs"""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "No tabs selected for deletion")
            return

        # Get indices of selected tabs in the original data
        indices_to_delete = []
        for item in selected_items:
            idx = int(self.tree.item(item)["text"]) - 1
            if 0 <= idx < len(self.filtered_data):
                tab = self.filtered_data[idx]
                original_index = self.tabs_data.index(tab)
                indices_to_delete.append(original_index)

        count = len(indices_to_delete)
        if messagebox.askyesno("Confirm Deletion", f"Delete {count} selected tabs?"):
            # Sort indices in reverse order to avoid index shifting issues
            for index in sorted(indices_to_delete, reverse=True):
                del self.tabs_data[index]

            self.on_search_changed()  # Refresh filtered data
            self.status_label.config(text=f"Deleted {count} tabs")

    def save_filtered(self):
        """Save filtered/remaining tabs"""
        if not self.tabs_data:
            messagebox.showwarning("No Data", "No data to save")
            return

        filename = filedialog.asksaveasfilename(
            title="Save Filtered Tabs",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )

        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    for tab in self.tabs_data:
                        f.write(f"{tab['url']} | {tab['title']}\n")

                messagebox.showinfo(
                    "Success",
                    f"Saved {len(self.tabs_data)} tabs to {os.path.basename(filename)}",
                )

            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {str(e)}")

    def export_json(self):
        """Export tabs as JSON"""
        if not self.tabs_data:
            messagebox.showwarning("No Data", "No data to export")
            return

        filename = filedialog.asksaveasfilename(
            title="Export as JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )

        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(self.tabs_data, f, indent=2, ensure_ascii=False)

                messagebox.showinfo(
                    "Success",
                    f"Exported {len(self.tabs_data)} tabs to {os.path.basename(filename)}",
                )

            except Exception as e:
                messagebox.showerror("Error", f"Failed to export file: {str(e)}")


def main():
    root = tk.Tk()
    app = OneTabManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
