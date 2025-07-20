import streamlit as st
import requests
import csv
import time
import pandas as pd
import subprocess
import os

# =============================================
# Streamlit App Configuration
# =============================================
st.set_page_config(layout="wide", page_title="Sistem Rekomendasi Hero Dota 2")

st.title("Sistem Rekomendasi Hero Dota 2 Berdasarkan Pola Pick dan Fitur Hero")
st.write("Aplikasi ini merekomendasikan hero Dota 2 selanjutnya berdasarkan hero yang sudah dipilih, menggunakan kombinasi algoritma PrefixSpan (untuk pola pick) dan Content-Based Filtering (untuk fitur hero).")

# =============================================
# Helper Functions (dari skripsi_demo_fix.py)
# =============================================

@st.cache_data(ttl=3600) # Cache data dari OpenDota untuk 1 jam
def get_recent_match_ids(n=30):
    url = "https://api.opendota.com/api/publicMatches"
    try:
        data = requests.get(url).json()
        return [m['match_id'] for m in data[:n]]
    except requests.exceptions.RequestException as e:
        st.error(f"Gagal mengambil data match terbaru dari OpenDota: {e}")
        return []

def get_hero_picks_from_match(mid):
    match = requests.get(f"https://api.opendota.com/api/matches/{mid}").json()
    if 'picks_bans' not in match: return []
    picks = sorted([x for x in match['picks_bans'] if x['is_pick']], key=lambda x: x['order'])
    return [str(p['hero_id']) for p in picks]

def save_matches(match_ids, filename="matches.csv"):
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["match_id", "hero_pick_sequence"])
        for mid in match_ids:
            picks = get_hero_picks_from_match(mid)
            if picks:
                writer.writerow([mid, ' '.join(picks)])
            time.sleep(0.1) # Kurangi delay untuk demo, bisa disesuaikan
    return filename

def convert_to_spmf(input_file, output_file="spmf_input.txt"):
    try:
        with open(input_file) as f:
            lines = f.readlines()[1:] # Skip header
        with open(output_file, 'w') as f:
            for line in lines:
                seq = line.strip().split(',')[1].split()
                f.write(' -1 '.join(seq) + ' -1 -2\n')
        return output_file
    except FileNotFoundError:
        st.error(f"File {input_file} tidak ditemukan.")
        return None

def run_spmf(input_path, output_path="spmf_output.txt", min_support=0.01): # Sesuaikan min_support jika terlalu sedikit/banyak pola
    # Pastikan spmf.jar ada di direktori yang sama atau PATH
    spmf_jar_path = "spmf.jar" # Asumsikan spmf.jar ada di direktori root project
    if not os.path.exists(spmf_jar_path):
        st.error(f"File {spmf_jar_path} tidak ditemukan. Mohon unggah atau pastikan file tersebut ada.")
        return None

    cmd = f"java -jar {spmf_jar_path} run PrefixSpan {input_path} {output_path} {min_support}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        # st.code(result.stdout) # Untuk debugging SPMF
        if result.stderr:
            st.error(f"SPMF Error: {result.stderr}")
        return output_path
    except subprocess.CalledProcessError as e:
        st.error(f"Gagal menjalankan SPMF: {e}")
        st.code(e.stdout)
        st.code(e.stderr)
        return None
    except FileNotFoundError:
        st.error("Perintah 'java' tidak ditemukan. Pastikan Java (JRE/JDK) terinstal dan ada di PATH.")
        return None

def read_spmf_output(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path) as f:
        lines = f.readlines()
    patterns = []
    for line in lines:
        pattern_str = line.split(" #SUP:")[0].replace(" -1", "").strip()
        if pattern_str:
            pattern = pattern_str.split()
            patterns.append(pattern)
    return patterns

@st.cache_data(ttl=86400) # Cache hero stats untuk 24 jam
def get_hero_features():
    url = "https://api.opendota.com/api/heroStats"
    try:
        data = requests.get(url).json()
        attr_map = {
            "str": "Strength", "agi": "Agility", "int": "Intelligence", "all": "Universal"
        }
        hero_list = []
        for h in data:
            hero_list.append({
                "hero_id": str(h["id"]),
                "hero_name": h["localized_name"],
                "attack_type": h["attack_type"],
                "primary_attr": attr_map.get(h["primary_attr"], "Unknown"),
                "role": h["roles"][0] if h["roles"] else "Unknown"
            })
        df = pd.DataFrame(hero_list)
        df['hero_id'] = df['hero_id'].astype(str) # Pastikan hero_id adalah string
        return df
    except requests.exceptions.RequestException as e:
        st.error(f"Gagal mengambil data hero dari OpenDota: {e}")
        return pd.DataFrame()

def recommend_spmf(current_picks, patterns, hero_id_map):
    current_picks_str = [str(p) for p in current_picks]
    scores = {}
    for pattern in patterns:
        # Periksa apakah pola dimulai dengan current_picks
        if len(pattern) > len(current_picks_str) and pattern[:len(current_picks_str)] == current_picks_str:
            next_hero = pattern[len(current_picks_str)]
            scores[next_hero] = scores.get(next_hero, 0) + 1 # Hitung frekuensi pola
    if not scores:
        return None
    # Pilih hero dengan skor tertinggi
    best_id = max(scores, key=scores.get)
    return best_id, hero_id_map.get(best_id, best_id), scores[best_id]

def get_similar_hero(last_hero_id, hero_features_df, hero_id_map):
    df = hero_features_df
    if last_hero_id not in df['hero_id'].values:
        return None

    row = df[df.hero_id == last_hero_id].iloc[0]

    # Cari hero lain dengan fitur yang sama (tipe serangan, atribut utama, peran)
    same_features_heroes = df[
        (df.attack_type == row.attack_type) &
        (df.primary_attr == row.primary_attr) &
        (df.role == row.role) &
        (df.hero_id != last_hero_id) # Jangan rekomendasikan hero itu sendiri
    ]

    if same_features_heroes.empty:
        return None

    # Pilih secara acak dari hero dengan fitur mirip
    pick = same_features_heroes.sample(1).iloc[0]
    return str(pick.hero_id), pick.hero_name

def hybrid_recommendation(picks, patterns, hero_features_df, hero_id_map):
    spmf_result = recommend_spmf(picks, patterns, hero_id_map)

    if spmf_result:
        spmf_id, spmf_name, spmf_score = spmf_result
        return spmf_id, spmf_name
    else:
        # Bagian ini yang diubah: Menghapus pesan st.info sebelumnya.
        if picks:
            last_hero_id = picks[-1]
            cbf_result = get_similar_hero(last_hero_id, hero_features_df, hero_id_map)
            if cbf_result:
                cbf_id, cbf_name = cbf_result
                return cbf_id, cbf_name
            else:
                return None
        return None

# Fungsi untuk menampilkan gambar hero
def show_hero_image(hero_name, width=80):
    if hero_name:
        name_for_url = hero_name.lower().replace(" ", "_").replace("'", "") # Handle nama hero seperti "Nature's Prophet"
        url = f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/{name_for_url}.png"
        st.image(url, width=width, caption=hero_name)

# =============================================
# Streamlit UI
# =============================================

# --- Load Data Hero ---
hero_features_df = get_hero_features()
if hero_features_df.empty:
    st.error("Tidak dapat memuat data hero. Harap coba lagi nanti.")
    st.stop() # Hentikan aplikasi jika data hero tidak tersedia

hero_id_map = {str(row.hero_id): row.hero_name for _, row in hero_features_df.iterrows()}
name_to_id_map = {v: k for k, v in hero_id_map.items()}

# Pilihan hero untuk dropdown
hero_options_with_none = [("Pilih Hero...", None)] + sorted([(f"{row.hero_name}", row.hero_id) for _, row in hero_features_df.iterrows()], key=lambda x: x[0])

st.sidebar.header("Konfigurasi Data dan Model")
# Tombol untuk menjalankan proses pengumpulan data dan pelatihan SPMF
if st.sidebar.button("Perbarui Data & Latih Model (Mungkin butuh waktu lama!)"):
    with st.spinner("Mengumpulkan data match terbaru dan melatih model PrefixSpan..."):
        match_ids = get_recent_match_ids(50) # Ambil lebih banyak data untuk hasil yang lebih baik
        if match_ids:
            matches_csv_file = save_matches(match_ids)
            spmf_input_file = convert_to_spmf(matches_csv_file)
            if spmf_input_file:
                spmf_output_file = run_spmf(spmf_input_file, min_support=0.005) # Sesuaikan min_support
                if spmf_output_file:
                    patterns = read_spmf_output(spmf_output_file)
                    st.session_state['patterns'] = patterns # Simpan pola di session_state
                    st.session_state['data_trained'] = True
                    st.success(f"Data dan model berhasil diperbarui! Ditemukan {len(patterns)} pola.")
                else:
                    st.error("Gagal melatih model SPMF.")
            else:
                st.error("Gagal mengkonversi data ke format SPMF.")
        else:
            st.warning("Tidak ada match yang ditemukan untuk diolah.")

# Inisialisasi patterns di session_state jika belum ada atau jika baru pertama kali dijalankan
if 'patterns' not in st.session_state:
    st.session_state['patterns'] = []
    st.session_state['data_trained'] = False

# Jika model belum dilatih atau data belum diperbarui
if not st.session_state['data_trained']:
    st.warning("Data rekomendasi belum diperbarui. Silakan klik 'Perbarui Data & Latih Model' di sidebar untuk mendapatkan rekomendasi terbaru.")
    # Coba baca pola dari file jika ada (misal dari deployment sebelumnya)
    if os.path.exists("spmf_output.txt"):
        st.session_state['patterns'] = read_spmf_output("spmf_output.txt")
        st.session_state['data_trained'] = True
        st.info("Pola dari sesi sebelumnya berhasil dimuat.")
    else:
        st.stop() # Hentikan eksekusi lebih lanjut jika tidak ada pola

st.subheader("Pilih Hero yang Sudah Dipilih:")

col1, col2, col3, col4 = st.columns(4)

with col1:
    hero1_name = st.selectbox('Hero 1 (Wajib):', hero_options_with_none, key='hero1_select')
    hero1_id = hero1_name[1] if hero1_name else None
    if hero1_id: show_hero_image(hero_id_map[hero1_id])

with col2:
    hero2_name = st.selectbox('Hero 2 (Wajib):', hero_options_with_none, key='hero2_select')
    hero2_id = hero2_name[1] if hero2_name else None
    if hero2_id: show_hero_image(hero_id_map[hero2_id])

with col3:
    hero3_name = st.selectbox('Hero 3 (Opsional):', hero_options_with_none, key='hero3_select')
    hero3_id = hero3_name[1] if hero3_name else None
    if hero3_id: show_hero_image(hero_id_map[hero3_id])

with col4:
    hero4_name = st.selectbox('Hero 4 (Opsional):', hero_options_with_none, key='hero4_select')
    hero4_id = hero4_name[1] if hero4_name else None
    if hero4_id: show_hero_image(hero_id_map[hero4_id])

# Kumpulkan hero yang dipilih
current_picks = []
if hero1_id: current_picks.append(str(hero1_id))
if hero2_id: current_picks.append(str(hero2_id))
if hero3_id: current_picks.append(str(hero3_id))
if hero4_id: current_picks.append(str(hero4_id))

st.markdown("---")
st.subheader("Hasil Rekomendasi:")

if st.button("Dapatkan Rekomendasi Hero"):
    if len(current_picks) < 2:
        st.warning("Minimal pilih 2 hero untuk mendapatkan rekomendasi.")
    else:
        st.info(f"Hero yang dipilih: {', '.join([hero_id_map.get(p, p) for p in current_picks])}")
        patterns_to_use = st.session_state['patterns']
        if not patterns_to_use:
            st.error("Model belum dilatih atau tidak ada pola yang ditemukan. Silakan perbarui data terlebih dahulu.")
        else:
            with st.spinner("Mencari rekomendasi..."):
                recommended_hero = hybrid_recommendation(current_picks, patterns_to_use, hero_features_df, hero_id_map)

                if recommended_hero:
                    st.success(f"**Rekomendasi Hero Selanjutnya:**")
                    col_rec1, col_rec2 = st.columns([1, 4])
                    with col_rec1:
                        show_hero_image(recommended_hero[1], width=150)
                    with col_rec2:
                        st.markdown(f"## {recommended_hero[1]}")
                        st.write(f"ID Hero: {recommended_hero[0]}")
                        st.markdown("---")
                        st.info("Setelah melihat rekomendasi ini, silakan berikan pendapat Anda apakah rekomendasi ini **sesuai dengan meta (keadaan hero populer/kuat) saat ini** atau tidak.")
                        st.markdown("Anda bisa mengisi kuesioner Anda di sini: [Link Kuesioner Anda]") # Ganti dengan link kuesioner Anda
                else:
                    st.warning("Tidak ditemukan rekomendasi hero berdasarkan pilihan saat ini.")

st.markdown("---")
st.markdown("P.S.: Data diambil dari OpenDota API. Model PrefixSpan dilatih ulang setiap kali tombol 'Perbarui Data & Latih Model' ditekan.")
