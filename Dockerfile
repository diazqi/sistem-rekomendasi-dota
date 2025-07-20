# Gunakan base image Debian yang Streamlit biasanya pakai
FROM python:3.9-slim-bullseye

# Perbarui APT dan instal dependensi yang diperlukan untuk mengunduh Java secara manual
# Ini termasuk curl untuk mengunduh, dpkg untuk menginstal .deb, dan apt-transport-https
# Kemudian instal Java 21 dari paket .deb yang diunduh langsung dari Oracle.
# Ini adalah cara yang lebih andal untuk mendapatkan Java 21 di lingkungan yang tidak memiliki paketnya di repo standar.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates apt-transport-https && \
    curl -fSL https://download.oracle.com/java/21/latest/jdk-21_linux-x64_bin.deb -o /tmp/jdk-21.deb && \
    dpkg -i /tmp/jdk-21.deb || apt-get install -f -y && \
    rm /tmp/jdk-21.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Setel JAVA_HOME dan tambahkan Java ke PATH
# Default lokasi instalasi Oracle JDK 21 di Debian/Ubuntu
ENV JAVA_HOME="/usr/lib/jvm/jdk-21"
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Verifikasi instalasi Java (ini akan muncul di log deployment)
RUN java -version

# Instal dependensi Python dari requirements.txt
COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Salin semua file aplikasi Anda (termasuk app.py, spmf.jar) ke working directory di dalam container
COPY . .

# Perintah untuk menjalankan aplikasi Streamlit
EXPOSE 8501
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
