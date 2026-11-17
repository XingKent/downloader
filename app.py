import queue
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import imageio_ffmpeg
import yt_dlp

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

PLATAFORMAS = {
    "youtube": {
        "nome": "YouTube",
        "cor": "#E62117",
        "regex": r"^https?://((www|m|music)\.)?(youtube\.com|youtu\.be)/.+",
        "exemplo": "https://www.youtube.com/watch?v=XXXXXXXXXXX",
    },
    "x": {
        "nome": "X (Twitter)",
        "cor": "#1D9BF0",
        "regex": r"^https?://(www\.|mobile\.)?(twitter|x)\.com/.+",
        "exemplo": "https://x.com/usuario/status/123456789",
    },
    "instagram": {
        "nome": "Instagram",
        "cor": "#C13584",
        "regex": r"^https?://(www\.)?instagram\.com/.+",
        "exemplo": "https://www.instagram.com/reel/XXXXXXXXXXX/",
    },
}

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Seletor(tk.Frame):
    """Seletor segmentado: um botão por plataforma (apenas um ativo)."""

    def __init__(self, master, bg, command=None):
        super().__init__(master, bg=bg)
        self.command = command
        self.valor = "youtube"
        self.botoes = {}
        for chave, p in PLATAFORMAS.items():
            b = tk.Label(
                self, text=p["nome"], font=("Segoe UI", 10, "bold"),
                padx=16, pady=7, cursor="hand2", bd=1, relief="solid",
            )
            b.pack(side="left")
            b.bind("<Button-1>", lambda _e, k=chave: self.escolher(k))
            self.botoes[chave] = b
        self.desenhar()

    def escolher(self, chave):
        if chave == self.valor:
            return
        self.valor = chave
        self.desenhar()
        if self.command:
            self.command(chave)

    def desenhar(self):
        for chave, b in self.botoes.items():
            if chave == self.valor:
                b.config(bg=PLATAFORMAS[chave]["cor"], fg="white")
            else:
                b.config(bg="#EDEDED", fg="#555555")


class App:
    def __init__(self, root):
        self.root = root
        self.fila = queue.Queue()
        self.ocupado = False

        root.title("Baixador de Vídeos - YouTube, X e Instagram")
        root.geometry("560x330")
        root.resizable(False, False)
        bg = root.cget("bg")

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)

        # --- Seletor de plataforma ---
        self.seletor = Seletor(frame, bg=bg)
        self.seletor.pack(pady=(0, 15))

        # --- Link ---
        ttk.Label(frame, text="Link do vídeo:").pack(anchor="w")
        self.var_url = tk.StringVar()
        self.entry = ttk.Entry(frame, textvariable=self.var_url, font=("Segoe UI", 10))
        self.entry.pack(fill="x", pady=(2, 10))

        # --- Cookies (ajuda no Instagram) ---
        linha2 = ttk.Frame(frame)
        linha2.pack(fill="x", pady=(0, 10))
        ttk.Label(linha2, text="Usar login do navegador (opcional):").pack(side="left")
        self.var_cookies = tk.StringVar(value="Nenhum")
        ttk.Combobox(
            linha2, textvariable=self.var_cookies, state="readonly", width=10,
            values=["Nenhum", "chrome", "firefox", "edge", "brave"],
        ).pack(side="left", padx=8)

        # --- Botão baixar ---
        self.btn = ttk.Button(frame, text="Baixar", command=self.ao_clicar_baixar)
        self.btn.pack(pady=5)

        # --- Progresso / status ---
        self.barra = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.barra.pack(fill="x", pady=(10, 4))
        self.var_status = tk.StringVar(value="Escolha a plataforma e cole o link.")
        ttk.Label(frame, textvariable=self.var_status, wraplength=510).pack(anchor="w")

        self.root.after(100, self.processar_fila)

    # ---------- Interface ----------
    def plataforma(self):
        return self.seletor.valor

    def travar(self, travado):
        self.ocupado = travado
        self.btn.config(state="disabled" if travado else "normal")
        self.entry.config(state="disabled" if travado else "normal")

    def ao_clicar_baixar(self):
        url = self.var_url.get().strip()
        p = PLATAFORMAS[self.plataforma()]
        if not url:
            messagebox.showwarning("Atenção", "Cole o link do vídeo primeiro.")
            return
        if not re.match(p["regex"], url):
            messagebox.showwarning(
                "Link inválido",
                f"O link não parece ser do {p['nome']}.\nExemplo: {p['exemplo']}",
            )
            return

        self.travar(True)
        self.barra.config(mode="indeterminate")
        self.barra.start(12)
        self.var_status.set("Buscando informações do vídeo...")
        threading.Thread(target=self.buscar_info, args=(url,), daemon=True).start()

    def opcoes_base(self):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": FFMPEG,
            "noplaylist": True,
        }
        nav = self.var_cookies.get()
        if nav != "Nenhum":
            opts["cookiesfrombrowser"] = (nav,)
        return opts

    # ---------- Threads ----------
    def buscar_info(self, url):
        try:
            opts = self.opcoes_base()
            opts["skip_download"] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist" and info.get("entries"):
                entradas = [e for e in info["entries"] if e]
                primeiro = entradas[0]
                total = len(entradas)
            else:
                primeiro, total = info, 1

            alturas = sorted(
                {
                    f["height"]
                    for f in primeiro.get("formats", [])
                    if f.get("height") and f.get("vcodec") not in (None, "none")
                },
                reverse=True,
            )
            titulo = primeiro.get("title") or info.get("title") or "Vídeo"
            self.fila.put(("info", url, titulo, alturas, total))
        except Exception as e:  # noqa: BLE001
            self.fila.put(("erro", self.limpar_erro(e)))

    def baixar(self, url, escolha, pasta):
        def hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total:
                    pct = d.get("downloaded_bytes", 0) / total * 100
                    vel = d.get("_speed_str", "").strip()
                    self.fila.put(("progresso", pct, f"Baixando... {pct:.0f}% {vel}"))
            elif d["status"] == "finished":
                self.fila.put(("status", "Processando arquivo..."))

        try:
            opts = self.opcoes_base()
            opts.update(
                {
                    "outtmpl": f"{pasta}/%(title).80s [%(id)s].%(ext)s",
                    "progress_hooks": [hook],
                    "restrictfilenames": False,
                    "windowsfilenames": True,
                }
            )
            if escolha == "mp3":
                opts["format"] = "bestaudio/best"
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ]
            elif escolha == "melhor":
                opts["format"] = "bv*+ba/b"
                opts["merge_output_format"] = "mp4"
            else:
                h = int(escolha)
                opts["format"] = f"bv*[height<={h}]+ba/b[height<={h}]/b"
                opts["merge_output_format"] = "mp4"

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self.fila.put(("concluido", pasta))
        except Exception as e:  # noqa: BLE001
            self.fila.put(("erro", self.limpar_erro(e)))

    @staticmethod
    def limpar_erro(e):
        return ANSI.sub("", str(e)).strip()

    # ---------- Fila (thread -> interface) ----------
    def processar_fila(self):
        try:
            while True:
                msg = self.fila.get_nowait()
                tipo = msg[0]
                if tipo == "info":
                    _, url, titulo, alturas, total = msg
                    self.parar_indeterminado()
                    self.var_status.set(f"Pronto: {titulo}")
                    self.mostrar_opcoes(url, titulo, alturas, total)
                elif tipo == "progresso":
                    self.barra.config(mode="determinate")
                    self.barra["value"] = msg[1]
                    self.var_status.set(msg[2])
                elif tipo == "status":
                    self.var_status.set(msg[1])
                    self.barra.config(mode="indeterminate")
                    self.barra.start(12)
                elif tipo == "concluido":
                    self.parar_indeterminado()
                    self.barra["value"] = 100
                    self.var_status.set("Download concluído!")
                    self.travar(False)
                    messagebox.showinfo("Concluído", f"Arquivo salvo em:\n{msg[1]}")
                elif tipo == "erro":
                    self.parar_indeterminado()
                    self.barra["value"] = 0
                    self.var_status.set("Erro ao processar.")
                    self.travar(False)
                    dica = ""
                    if self.plataforma() == "instagram":
                        dica = (
                            "\n\nDica: o Instagram costuma exigir login. Faça login no "
                            "navegador e escolha-o em 'Usar login do navegador'."
                        )
                    elif self.plataforma() == "youtube":
                        dica = (
                            "\n\nDica: se o YouTube pedir confirmação de que você não é um "
                            "robô ou o vídeo for restrito, escolha seu navegador em "
                            "'Usar login do navegador'. Se o erro citar 'JavaScript runtime', "
                            "instale o Deno (https://deno.com) ou o Node.js e tente de novo."
                        )
                    messagebox.showerror("Erro", msg[1][:700] + dica)
        except queue.Empty:
            pass
        self.root.after(100, self.processar_fila)

    def parar_indeterminado(self):
        self.barra.stop()
        self.barra.config(mode="determinate")

    # ---------- Janela de opções ----------
    def mostrar_opcoes(self, url, titulo, alturas, total):
        win = tk.Toplevel(self.root)
        win.title("Opções de download")
        win.transient(self.root)
        win.resizable(False, False)
        win.grab_set()

        f = ttk.Frame(win, padding=20)
        f.pack(fill="both", expand=True)

        t = titulo if len(titulo) <= 60 else titulo[:57] + "..."
        ttk.Label(f, text=t, font=("Segoe UI", 10, "bold"), wraplength=360).pack(anchor="w")
        if total > 1:
            ttk.Label(f, text=f"Este link contém {total} vídeos; todos serão baixados.").pack(anchor="w")
        ttk.Label(f, text="Escolha o formato:").pack(anchor="w", pady=(10, 4))

        var = tk.StringVar()
        if alturas:
            for i, h in enumerate(alturas):
                ttk.Radiobutton(f, text=f"Vídeo {h}p (MP4)", value=str(h), variable=var).pack(anchor="w")
                if i == 0:
                    var.set(str(h))
        else:
            ttk.Radiobutton(f, text="Vídeo - melhor qualidade (MP4)", value="melhor", variable=var).pack(anchor="w")
            var.set("melhor")
        ttk.Separator(f).pack(fill="x", pady=6)
        ttk.Radiobutton(f, text="Somente áudio - converter para MP3", value="mp3", variable=var).pack(anchor="w")

        botoes = ttk.Frame(f)
        botoes.pack(pady=(15, 0))

        def cancelar():
            win.destroy()
            self.var_status.set("Cancelado.")
            self.travar(False)

        def continuar():
            escolha = var.get()
            win.destroy()
            pasta = filedialog.askdirectory(title="Escolha a pasta para salvar")
            if not pasta:
                self.var_status.set("Cancelado: nenhuma pasta escolhida.")
                self.travar(False)
                return
            self.barra["value"] = 0
            self.var_status.set("Iniciando download...")
            threading.Thread(target=self.baixar, args=(url, escolha, pasta), daemon=True).start()

        ttk.Button(botoes, text="Baixar", command=continuar).pack(side="left", padx=5)
        ttk.Button(botoes, text="Cancelar", command=cancelar).pack(side="left", padx=5)
        win.protocol("WM_DELETE_WINDOW", cancelar)

        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()