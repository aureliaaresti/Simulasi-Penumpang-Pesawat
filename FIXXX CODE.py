import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox
import heapq
import itertools
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

FILE_PATH = 'DATA SET PROJECK SDA SMT 2.xlsx'
SHEET_NAME = 'Data Penumpang'

NUM_CHECKIN_SERVERS = 2
NUM_SECURITY_SERVERS = 2
NUM_BOARDING_SERVERS = 2

SIM_SPEED = 100

KELAS_SCORE = {'First Class': 1, 'Bisnis': 2, 'Ekonomi': 3}
STATUS_SCORE = {'Prioritas': 1, 'Reguler': 2}

def load_passengers():
    df = pd.read_excel(FILE_PATH, sheet_name=SHEET_NAME, header=1)
    df.columns = df.columns.str.replace('\n', ' ', regex=False).str.strip()

    def cari_kolom(kata_kunci):
        for col in df.columns:
            if kata_kunci.lower() in col.lower():
                return col
        raise KeyError(f"Kolom yang mengandung '{kata_kunci}' tidak ditemukan. Kolom yang tersedia: {list(df.columns)}")

    col_mulai = cari_kolom('Mulai Check-in')
    col_checkin_dur = cari_kolom('Durasi Check-in')
    col_security_dur = cari_kolom('Durasi Security')
    col_boarding_dur = cari_kolom('Durasi Boarding')
    col_kelas = cari_kolom('Kelas Tiket')
    col_prioritas = cari_kolom('Prioritas Antrian')

    df[col_mulai] = pd.to_datetime(df[col_mulai], errors='coerce')
    df = df.dropna(subset=[col_mulai])

    df['PriorityScore'] = (
        df[col_kelas].map(KELAS_SCORE) * 10 +
        df[col_prioritas].map(STATUS_SCORE)
    )

    base_time = df[col_mulai].min()
    df['ArrivalSeconds'] = (df[col_mulai] - base_time).dt.total_seconds().astype(int)
    df_sorted = df.sort_values('ArrivalSeconds').reset_index(drop=True)

    passengers = []
    for idx, row in df_sorted.iterrows():
        passengers.append({
            'ID': row['ID Penumpang'],
            'Nama': row['Nama Penumpang'],
            'Kelas': row[col_kelas],
            'Tipe': row['Tipe Penumpang'],
            'Prioritas': row[col_prioritas],
            'priority_score': row['PriorityScore'],
            'arrival_seq': idx,
            'arrival_time': int(row['ArrivalSeconds']),
            'checkin_duration': int(row[col_checkin_dur]) * 60,
            'security_duration': int(row[col_security_dur]) * 60,
            'boarding_duration': int(row[col_boarding_dur]) * 60,
            'start_time': None,
            'finish_time': None,
        })
    return passengers

all_passengers = load_passengers()

# Antrian priority queue (semua langsung diisi saat reset, tanpa jadwal)
queue_checkin = []
queue_security = []
queue_boarding = []

servers_checkin = [None] * NUM_CHECKIN_SERVERS
servers_security = [None] * NUM_SECURITY_SERVERS
servers_boarding = [None] * NUM_BOARDING_SERVERS

completed = []
event_log = []
simulation_time = 0
simulation_running = False
simulation_paused = False
after_id = None

queue_history = []
uid_counter = itertools.count()

def log_event(message):
    timestamp = time.strftime("%H:%M:%S", time.gmtime(simulation_time))
    entry = f"[{timestamp}] {message}"
    event_log.append(entry)
    log_text.insert(tk.END, entry + "\n")
    log_text.see(tk.END)
    if len(event_log) > 300:
        log_text.delete(1.0, 2.0)

def push_queue(heap, passenger):
    uid = next(uid_counter)
    heapq.heappush(heap, (passenger['priority_score'], uid, passenger))

def pop_queue(heap):
    _, _, p = heapq.heappop(heap)
    return p

def update_display():
    list_checkin.delete(0, tk.END)
    list_security.delete(0, tk.END)
    list_boarding.delete(0, tk.END)
    list_completed.delete(0, tk.END)

    for i, (score, uid, p) in enumerate(sorted(queue_checkin), 1):
        list_checkin.insert(tk.END, f"{i}. {p['Nama']} ({p['Kelas']} - {p['Prioritas']})")
    for i, (score, uid, p) in enumerate(sorted(queue_security), 1):
        list_security.insert(tk.END, f"{i}. {p['Nama']} ({p['Kelas']} - {p['Prioritas']})")
    for i, (score, uid, p) in enumerate(sorted(queue_boarding), 1):
        list_boarding.insert(tk.END, f"{i}. {p['Nama']} ({p['Kelas']} - {p['Prioritas']})")

    for i, s in enumerate(servers_checkin):
        if s is None:
            status_checkin[i].config(text="Tersedia", bg="#00ff6a")
        else:
            p, rem = s
            status_checkin[i].config(text=f"{p['Nama']} ({rem:.0f}s)", bg='#f39c12')
    for i, s in enumerate(servers_security):
        if s is None:
            status_security[i].config(text="Tersedia", bg="#00ff6a")
        else:
            p, rem = s
            status_security[i].config(text=f"{p['Nama']} ({rem:.0f}s)", bg='#f39c12')
    for i, s in enumerate(servers_boarding):
        if s is None:
            status_boarding[i].config(text="Tersedia", bg="#00ff6a")
        else:
            p, rem = s
            status_boarding[i].config(text=f"{p['Nama']} ({rem:.0f}s)", bg='#f39c12')

    for i, p in enumerate(completed, 1):
        list_completed.insert(tk.END, f"{i}. {p['Nama']} ({p['Kelas']})")

    waiting_total = len(queue_checkin) + len(queue_security) + len(queue_boarding)
    lbl_stats.config(
        text=f"Mode: Paralel (Prioritas) | Waktu: {simulation_time}s | Menunggu: {waiting_total} | Selesai: {len(completed)}/{len(all_passengers)}"
    )

# Tidak ada proses kedatangan bertahap, semua penumpang sudah di antrian sejak reset
def process_arrivals():
    pass  # kosong, karena tidak digunakan

def assign_to_servers():
    for i in range(NUM_CHECKIN_SERVERS):
        if servers_checkin[i] is None and queue_checkin:
            p = pop_queue(queue_checkin)
            if p['start_time'] is None:
                p['start_time'] = simulation_time
            servers_checkin[i] = (p, p['checkin_duration'])
            log_event(f"Check-in Server {i+1}: {p['Nama']} ({p['Kelas']}, {p['Prioritas']}) durasi {p['checkin_duration']}s")
    for i in range(NUM_SECURITY_SERVERS):
        if servers_security[i] is None and queue_security:
            p = pop_queue(queue_security)
            servers_security[i] = (p, p['security_duration'])
            log_event(f"Security Server {i+1}: {p['Nama']} ({p['Kelas']}, {p['Prioritas']}) durasi {p['security_duration']}s")
    for i in range(NUM_BOARDING_SERVERS):
        if servers_boarding[i] is None and queue_boarding:
            p = pop_queue(queue_boarding)
            servers_boarding[i] = (p, p['boarding_duration'])
            log_event(f"Boarding Gate {i+1}: {p['Nama']} ({p['Kelas']}, {p['Prioritas']}) durasi {p['boarding_duration']}s")

def update_servers_parallel(delta_time):
    for i in range(NUM_CHECKIN_SERVERS):
        if servers_checkin[i] is not None:
            p, rem = servers_checkin[i]
            rem -= delta_time
            if rem <= 0:
                servers_checkin[i] = None
                push_queue(queue_security, p)
                log_event(f"{p['Nama']} selesai Check-in -> antrian Security")
            else:
                servers_checkin[i] = (p, rem)
    for i in range(NUM_SECURITY_SERVERS):
        if servers_security[i] is not None:
            p, rem = servers_security[i]
            rem -= delta_time
            if rem <= 0:
                servers_security[i] = None
                push_queue(queue_boarding, p)
                log_event(f"{p['Nama']} selesai Security -> antrian Boarding")
            else:
                servers_security[i] = (p, rem)
    for i in range(NUM_BOARDING_SERVERS):
        if servers_boarding[i] is not None:
            p, rem = servers_boarding[i]
            rem -= delta_time
            if rem <= 0:
                servers_boarding[i] = None
                p['finish_time'] = simulation_time
                completed.append(p)
                log_event(f"{p['Nama']} SELESAI BOARDING (total selesai: {len(completed)})")
            else:
                servers_boarding[i] = (p, rem)

def check_simulation_done():
    return (not queue_checkin and
            not queue_security and
            not queue_boarding and
            all(s is None for s in servers_checkin) and
            all(s is None for s in servers_security) and
            all(s is None for s in servers_boarding))

def simulation_step():
    global simulation_time, after_id, simulation_running
    if not simulation_running or simulation_paused:
        return
    delta = 1
    simulation_time += delta

    # process_arrivals() tidak dipanggil karena semua sudah di antrian
    update_servers_parallel(delta)
    assign_to_servers()

    queue_history.append((simulation_time, len(queue_checkin), len(queue_security), len(queue_boarding)))
    update_display()

    if check_simulation_done():
        simulation_running = False
        log_event("=== SIMULASI SELESAI ===")
        show_statistics()
        btn_start.config(state=tk.NORMAL)
        btn_pause.config(state=tk.DISABLED)
        return
    after_id = root.after(SIM_SPEED, simulation_step)

def show_statistics():
    if not completed:
        return
    total_times = []
    by_class = {}
    by_priority = {}
    for p in completed:
        if p['finish_time'] and p['start_time']:
            total = p['finish_time'] - p['start_time']
            total_times.append(total)
            by_class.setdefault(p['Kelas'], []).append(total)
            by_priority.setdefault(p['Prioritas'], []).append(total)
    summary = [
        "Mode: Paralel (Multi-server dengan prioritas)",
        f"Total penumpang selesai: {len(completed)}",
        f"Waktu simulasi: {simulation_time} detik ({simulation_time//60} menit)",
        "\nRata-rata waktu per kelas:"
    ]
    for kls in ['First Class', 'Bisnis', 'Ekonomi']:
        if kls in by_class:
            avg = sum(by_class[kls]) / len(by_class[kls])
            summary.append(f"  {kls}: {avg:.0f} detik ({avg/60:.1f} menit) dari {len(by_class[kls])} org")
    summary.append("\nRata-rata per prioritas:")
    for prio in ['Prioritas', 'Reguler']:
        if prio in by_priority:
            avg = sum(by_priority[prio]) / len(by_priority[prio])
            summary.append(f"  {prio}: {avg:.0f} detik ({avg/60:.1f} menit)")
    if total_times:
        summary.append(f"\nRata-rata keseluruhan: {sum(total_times)/len(total_times):.0f} detik")
        summary.append(f"Tercepat: {min(total_times):.0f} detik | Terlama: {max(total_times):.0f} detik")
    messagebox.showinfo("Statistik Simulasi", "\n".join(summary))
    update_chart()

def update_chart():
    if not queue_history:
        return
    times = [h[0] for h in queue_history]
    ci = [h[1] for h in queue_history]
    sec = [h[2] for h in queue_history]
    bo = [h[3] for h in queue_history]
    ax.clear()
    ax.plot(times, ci, label='Check-in', color='#3498db')
    ax.plot(times, sec, label='Security', color='#e74c3c')
    ax.plot(times, bo, label='Boarding', color='#2ecc71')
    ax.set_xlabel('Waktu (detik)')
    ax.set_ylabel('Panjang Antrian')
    ax.set_title('Panjang Antrian per Waktu')
    ax.legend()
    ax.grid(True, alpha=0.3)
    canvas_chart.draw()

def start_simulation():
    global simulation_running, simulation_paused
    if simulation_running:
        return
    simulation_running = True
    simulation_paused = False
    btn_start.config(state=tk.DISABLED)
    btn_pause.config(state=tk.NORMAL)
    simulation_step()

def pause_simulation():
    global simulation_paused
    simulation_paused = True
    btn_start.config(state=tk.NORMAL)
    btn_pause.config(state=tk.DISABLED)

def resume_simulation():
    global simulation_paused
    if simulation_running and simulation_paused:
        simulation_paused = False
        btn_start.config(state=tk.DISABLED)
        btn_pause.config(state=tk.NORMAL)
        simulation_step()

def reset_simulation():
    global simulation_time, simulation_running, simulation_paused, after_id
    global queue_checkin, queue_security, queue_boarding
    global servers_checkin, servers_security, servers_boarding
    global completed, event_log, queue_history, uid_counter

    if after_id:
        root.after_cancel(after_id)

    simulation_running = False
    simulation_paused = False
    simulation_time = 0

    # Semua penumpang langsung masuk antrian check-in (tanpa jadwal)
    queue_checkin = []
    queue_security = []
    queue_boarding = []
    for p in all_passengers:
        push_queue(queue_checkin, p.copy())

    servers_checkin = [None] * NUM_CHECKIN_SERVERS
    servers_security = [None] * NUM_SECURITY_SERVERS
    servers_boarding = [None] * NUM_BOARDING_SERVERS

    completed = []
    event_log = []
    queue_history = []
    uid_counter = itertools.count()

    log_text.delete(1.0, tk.END)
    ax.clear()
    canvas_chart.draw()
    update_display()
    log_event("Simulasi direset. Semua penumpang dalam antrian check-in (prioritas).")
    btn_start.config(state=tk.NORMAL)
    btn_pause.config(state=tk.DISABLED)

# GUI
root = tk.Tk()
root.title("Simulasi Antrian Bandara - Multi-Queue Paralel dengan Prioritas")
root.geometry("1400x800")
root.configure(bg='#93c9ff')

tk.Label(root, text="SIMULASI ANTRIAN BANDARA", font=("Arial", 14, "bold"), bg="#93c9ff", fg='black').pack(pady=5)
tk.Label(root, text="Implementasi Priority Queue pada Multi-Queue Check-in, Security, Boarding", font=("Arial", 9), bg="#93c9ff", fg="#000000").pack()

ctrl_frame = tk.Frame(root, bg='#93c9ff')
ctrl_frame.pack(fill="x", padx=10, pady=5)

btn_start = tk.Button(ctrl_frame, text="Mulai Simulasi", command=start_simulation, bg="#3fff8f", fg='black', font=("Arial", 10, "bold"))
btn_start.pack(side=tk.LEFT, padx=5)
btn_pause = tk.Button(ctrl_frame, text="Jeda", command=pause_simulation, bg='#f39c12', fg='black', font=("Arial", 10, "bold"), state=tk.DISABLED)
btn_pause.pack(side=tk.LEFT, padx=5)
btn_resume = tk.Button(ctrl_frame, text="Lanjut", command=resume_simulation, bg='#3498db', fg='black', font=("Arial", 10, "bold"))
btn_resume.pack(side=tk.LEFT, padx=5)
btn_reset = tk.Button(ctrl_frame, text="Reset", command=reset_simulation, bg='#e74c3c', fg='black', font=("Arial", 10, "bold"))
btn_reset.pack(side=tk.LEFT, padx=5)
btn_stats = tk.Button(ctrl_frame, text="Lihat Statistik", command=show_statistics, bg='#1abc9c', fg='black', font=("Arial", 10, "bold"))
btn_stats.pack(side=tk.LEFT, padx=5)

lbl_stats = tk.Label(ctrl_frame, text="", font=("Arial", 10, "bold"), bg='#93c9ff', fg='black')
lbl_stats.pack(side=tk.RIGHT, padx=10)

main_frame = tk.Frame(root, bg='#93c9ff')
main_frame.pack(fill="both", expand=True, padx=10, pady=5)

left_frame = tk.Frame(main_frame, bg='#93c9ff')
left_frame.pack(side=tk.LEFT, fill="both", expand=True)

# Check-in
frame_ci = tk.LabelFrame(left_frame, text="CHECK-IN (Priority Queue)", font=("Arial", 10, "bold"), bg='#93c9ff', fg='black')
frame_ci.pack(fill="x", pady=3)
list_checkin = tk.Listbox(frame_ci, height=6, font=("Arial", 9))
list_checkin.pack(side=tk.LEFT, fill="both", expand=True, padx=5, pady=4)
server_ci_frame = tk.Frame(frame_ci, bg='#93c9ff')
server_ci_frame.pack(side=tk.RIGHT, padx=5)
status_checkin = []
for i in range(NUM_CHECKIN_SERVERS):
    lbl = tk.Label(server_ci_frame, text=f"Server {i+1}: Tersedia", font=("Arial", 9), bg='#2ecc71', width=24, relief="ridge")
    lbl.pack(pady=2)
    status_checkin.append(lbl)

# Security
frame_sec = tk.LabelFrame(left_frame, text="SECURITY (Priority Queue)", font=("Arial", 10, "bold"), bg='#93c9ff', fg='black')
frame_sec.pack(fill="x", pady=3)
list_security = tk.Listbox(frame_sec, height=6, font=("Arial", 9))
list_security.pack(side=tk.LEFT, fill="both", expand=True, padx=5, pady=4)
server_sec_frame = tk.Frame(frame_sec, bg='#93c9ff')
server_sec_frame.pack(side=tk.RIGHT, padx=5)
status_security = []
for i in range(NUM_SECURITY_SERVERS):
    lbl = tk.Label(server_sec_frame, text=f"Server {i+1}: Tersedia", font=("Arial", 9), bg='#2ecc71', width=24, relief="ridge")
    lbl.pack(pady=2)
    status_security.append(lbl)

# Boarding
frame_bo = tk.LabelFrame(left_frame, text="BOARDING (Priority Queue)", font=("Arial", 10, "bold"), bg='#93c9ff', fg='black')
frame_bo.pack(fill="x", pady=3)
list_boarding = tk.Listbox(frame_bo, height=6, font=("Arial", 9))
list_boarding.pack(side=tk.LEFT, fill="both", expand=True, padx=5, pady=4)
server_bo_frame = tk.Frame(frame_bo, bg='#93c9ff')
server_bo_frame.pack(side=tk.RIGHT, padx=5)
status_boarding = []
for i in range(NUM_BOARDING_SERVERS):
    lbl = tk.Label(server_bo_frame, text=f"Gate {i+1}: Tersedia", font=("Arial", 9), bg="#00ff6a", width=24, relief="ridge")
    lbl.pack(pady=2)
    status_boarding.append(lbl)

# Completed
frame_done = tk.LabelFrame(left_frame, text="PENUMPANG SELESAI", font=("Arial", 10, "bold"), bg='#93c9ff', fg='black')
frame_done.pack(fill="both", expand=True, pady=3)
list_completed = tk.Listbox(frame_done, height=6, font=("Arial", 9), bg='#d5f5e3')
list_completed.pack(fill="both", expand=True, padx=5, pady=4)

right_frame = tk.Frame(main_frame, bg='#93c9ff')
right_frame.pack(side=tk.RIGHT, fill="both", expand=True, padx=5)

log_frame = tk.LabelFrame(right_frame, text="LOG SIMULASI", font=("Arial", 10, "bold"), bg='#93c9ff', fg='black')
log_frame.pack(fill="both", expand=True)
log_text = tk.Text(log_frame, height=18, width=50, font=("Consolas", 8))
scroll_log = tk.Scrollbar(log_frame, command=log_text.yview)
log_text.configure(yscrollcommand=scroll_log.set)
scroll_log.pack(side=tk.RIGHT, fill=tk.Y)
log_text.pack(side=tk.LEFT, fill="both", expand=True)

chart_frame = tk.LabelFrame(right_frame, text="GRAFIK PANJANG ANTRIAN", font=("Arial", 10, "bold"), bg='#93c9ff', fg='black')
chart_frame.pack(fill="both", expand=True, pady=5)
fig, ax = plt.subplots(figsize=(5, 2.5))
fig.patch.set_facecolor('#93c9ff')
ax.set_facecolor('#93c9ff')
ax.tick_params(colors='white')
ax.xaxis.label.set_color('white')
ax.yaxis.label.set_color('white')
ax.title.set_color('white')
canvas_chart = FigureCanvasTkAgg(fig, master=chart_frame)
canvas_chart.get_tk_widget().pack(fill="both", expand=True)

reset_simulation()
root.mainloop()