<p align="center">
  <img src="img/kwipu_tagline_en.svg" width="384" alt="Kwipu — Hỏi ghi chú của bạn">
</p>

# Kwipu

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-orange.svg)](https://ollama.com/)
[![LlamaIndex](https://img.shields.io/badge/framework-LlamaIndex-purple.svg)](https://www.llamaindex.ai/)
[![Obsidian Compatible](https://img.shields.io/badge/Obsidian-compatible-7C3AED.svg)](https://obsidian.md/)
[![MCP Server](https://img.shields.io/badge/MCP-compatible-blue.svg)](https://modelcontextprotocol.io/)

[English](README.md) | [简体中文](README.zh-CN.md) | **Tiếng Việt**

Kwipu biến một thư mục tài liệu thành chỉ mục RAG đồ thị thuộc tính mà bạn có thể khám phá và truy vấn từ terminal tương tác, giao diện web 3D hoặc ứng dụng MCP. Kwipu hoạt động với cả thư mục tri thức thông thường lẫn vault theo phong cách Obsidian.

> **Về “hoàn toàn cục bộ”:** Kwipu có thể chạy hoàn toàn cục bộ khi bạn chọn LLM và mô hình embedding Ollama cục bộ. LLM mặc định có chủ đích là `gpt-oss:20b-cloud`, có thể gửi các đoạn tài liệu, ngữ cảnh được truy xuất và câu hỏi đến nhà cung cấp của mô hình. [Hãy chọn cloud hoặc local trước khi lập chỉ mục](#chọn-cloud-hay-local).

## Chọn cách sử dụng

| Tôi muốn… | Bắt đầu tại đây |
|---|---|
| Hỏi trực tiếp nội dung ghi chú trong terminal | [Sử dụng chỉ trong terminal](#sử-dụng-chỉ-trong-terminal) |
| Khám phá đồ thị và đặt câu hỏi từ trình duyệt | [Bắt đầu nhanh: giao diện web](#bắt-đầu-nhanh-giao-diện-web) |
| Sử dụng ghi chú của riêng tôi hoặc vault Obsidian | [Sử dụng thư mục tài liệu của bạn](#sử-dụng-thư-mục-tài-liệu-của-bạn) |
| Kết nối ứng dụng AI qua MCP | [Máy chủ MCP](#máy-chủ-mcp) |
| Cấu hình hoặc triển khai hệ thống | [Tham chiếu cấu hình](#tham-chiếu-cấu-hình) |
| Chạy kiểm thử hoặc đóng góp mã nguồn | [Thiết lập cho nhà phát triển](#thiết-lập-cho-nhà-phát-triển) |

## Kwipu làm được gì

- Xây dựng đồ thị thuộc tính từ tài liệu `.md`, `.txt`, `.pdf` và `.docx`.
- Trích xuất quan hệ ngữ nghĩa bằng LLM và quan hệ cấu trúc từ wikilink cùng YAML frontmatter.
- Kết hợp độ tương đồng vector, BM25, siêu dữ liệu thời gian và truy xuất từ đồng nghĩa tùy chọn.
- Gắn câu trả lời với các đoạn nguồn và trả về trích dẫn.
- Trực quan hóa thực thể, tài liệu và quan hệ trong đồ thị 3D tương tác.
- Theo dõi thư mục nguồn và cập nhật vùng lưu trữ bền vững một cách an toàn.
- Hỗ trợ các mẫu tiếng Anh, tiếng Ý, tiếng Pháp, tiếng Đức, tiếng Tây Ban Nha và tiếng Bồ Đào Nha.
- Cung cấp cùng một nguồn tri thức qua terminal, API web và MCP.

## Giao diện web

### 1. Đặt câu hỏi có căn cứ và mở nguồn trích dẫn

![Câu trả lời của Kwipu cùng đồ thị và phần xem trước nguồn](img/second%20brain.jpeg)

### 2. Tái dựng các thay đổi qua những cuộc họp và lần đánh giá

![Kwipu tái dựng dòng thời gian của dự án](img/second%20brain_2.jpeg)

### 3. So sánh con người, vai trò và các tài liệu làm căn cứ

![Kwipu so sánh vai trò trong dự án cùng trích dẫn](img/second%20brain_3.jpeg)

<details>
<summary>Ví dụ về terminal và Obsidian</summary>

![Kwipu trong terminal trả lời từ ghi chú dự án Obsidian](img/screen.png)

![Kwipu xây dựng lại sau khi cập nhật ghi chú cuộc họp Obsidian](img/screen_2.png)

</details>

## Chọn cloud hay local

Kwipu kết nối với một endpoint tương thích Ollama, mặc định là `http://localhost:11434`. Chỉ riêng việc dùng endpoint cục bộ **không** đảm bảo mô hình được thực thi cục bộ.

| Chế độ | LLM | Cách dữ liệu được xử lý | Trước lần sử dụng đầu tiên |
|---|---|---|---|
| Cloud mặc định | `gpt-oss:20b-cloud` | Ollama có thể chuyển tiếp ngữ cảnh và câu hỏi đến nhà cung cấp mô hình. Hãy xem xét chính sách của nhà cung cấp đó về quyền riêng tư, thời gian lưu giữ và vị trí dữ liệu. | `ollama pull gpt-oss:20b-cloud` |
| Ví dụ local | `qwen2.5:7b` | Suy luận vẫn diễn ra trên máy khi cả hai mô hình và endpoint Ollama đều ở cục bộ. | `ollama pull qwen2.5:7b` |

Cả hai chế độ đều dùng mô hình embedding cục bộ trong cấu hình mặc định:

```powershell
ollama pull nomic-embed-text
```

Endpoint Ollama từ xa sẽ gửi dữ liệu đến máy chủ đó. Kwipu yêu cầu HTTPS cho endpoint không phải loopback, trừ khi HTTP không an toàn được bật rõ ràng cho một mạng đáng tin cậy.

## Bắt đầu nhanh: giao diện web

Hướng dẫn thiết lập dưới đây dành cho Windows PowerShell. [Các lệnh tương đương trên Linux và macOS](#các-lệnh-tương-đương-trên-linux-và-macos) nằm ở phần tiếp theo. Nếu chỉ muốn dùng giao diện terminal, hãy thực hiện các bước 1–6 rồi dừng trước khi khởi động bridge và frontend.

### 1. Cài đặt và kiểm tra các điều kiện tiên quyết

Cài đặt:

- [Git](https://git-scm.com/downloads) hoặc tải repository dưới dạng tệp ZIP.
- [Python 3.12 trở lên](https://www.python.org/downloads/).
- [Ollama](https://ollama.com/download).
- [Node.js kèm npm](https://nodejs.org/) chỉ khi bạn muốn dùng giao diện web.

Mở PowerShell và kiểm tra các lệnh bạn cần:

```powershell
git --version
py -3.12 --version
ollama --version
node --version
npm --version
```

Nếu không tìm thấy một lệnh, hãy cài đặt điều kiện tiên quyết còn thiếu, mở cửa sổ PowerShell mới rồi chạy lại lệnh kiểm tra. Người chỉ dùng terminal không cần Node.js hoặc npm.

### 2. Tải Kwipu và cài đặt môi trường chạy

```powershell
git clone https://github.com/benmaster82/Kwipu.git
Set-Location .\Kwipu

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip==25.1.1
python -m pip install -r .\bridge\requirements.txt

# Web interface only:
npm --prefix .\frontend ci
```

`bridge/requirements.txt` bao gồm các dependency cốt lõi cho terminal, vì vậy một lần cài đặt Python có thể phục vụ cả hai giao diện. Nếu đã tải tệp ZIP, hãy giải nén rồi chạy các lệnh sau `git clone` từ thư mục `Kwipu` đã giải nén.

Nếu PowerShell chặn việc kích hoạt môi trường ảo, hãy áp dụng chính sách chỉ dành cho tiến trình này rồi thử lại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Thêm tài liệu

Repository đã bao gồm một bộ dữ liệu minh họa nhỏ trong `knowledge_base/examples`. Để dùng tệp của riêng bạn, hãy sao chép các tệp `.md`, `.txt`, `.pdf` hoặc `.docx` vào `knowledge_base` trước khi khởi động trình lập chỉ mục.

```text
Kwipu/
└── knowledge_base/
    ├── examples/
    └── your-notes/
        ├── project.md
        └── meeting-notes.pdf
```

Kwipu đọc tài liệu nguồn nhưng không ghi lại chúng.

### 4. Chuẩn bị các mô hình

Hãy chắc chắn Ollama đang chạy. Ứng dụng Ollama trên desktop có thể đã chạy dịch vụ; nếu chưa, hãy giữ lệnh sau chạy trong **Terminal 1**:

```powershell
ollama serve
```

Trong một cửa sổ PowerShell khác, hãy tải mô hình embedding và đúng một LLM:

```powershell
ollama pull nomic-embed-text

# Cloud default:
ollama pull gpt-oss:20b-cloud

# OR local-only example:
# ollama pull qwen2.5:7b
```

Mô hình cloud có thể yêu cầu bạn hoàn tất các bước về tài khoản hoặc đăng nhập Ollama. Không lập chỉ mục tài liệu nhạy cảm cho đến khi bạn đã chọn đúng chế độ thực thi mong muốn.

### 5. Dùng một cấu hình nhất quán

Các thiết lập được đọc khi mỗi tiến trình khởi động. Giá trị `$env:` của PowerShell chỉ áp dụng cho cửa sổ hiện tại, vì vậy hãy dán khối sau vào cả **terminal của indexer** và **terminal của bridge**.

```powershell
Set-Location "C:\path\to\Kwipu" # replace with your actual folder
.\.venv\Scripts\Activate.ps1

$env:KWIPU_ROOT_DIR = (Get-Location).Path
$env:KWIPU_KNOWLEDGE_DIR = "knowledge_base"
$env:KWIPU_STORAGE_DIR = "storage_graph"
$env:KWIPU_EMBED_MODEL = "nomic-embed-text"
$env:KWIPU_OLLAMA_BASE_URL = "http://localhost:11434"
$env:KWIPU_QUERY_MAX_LENGTH = "4000"

# Run exactly one of these two lines:
$env:KWIPU_LLM_MODEL = "gpt-oss:20b-cloud" # cloud default
# $env:KWIPU_LLM_MODEL = "qwen2.5:7b"       # local example
```

Nếu chọn mô hình local, hãy comment dòng cloud và bỏ comment dòng local trong **cả hai** terminal.

> Với thiết lập dùng chung terminal/web, nên ưu tiên biến môi trường thay vì `geode_graph.py --llm-model`. Các cờ CLI chỉ cấu hình tiến trình terminal đó; chúng không cấu hình bridge.

### 6. Khởi động indexer và giao diện terminal — Terminal 2

Sau khi áp dụng khối cấu hình:

```powershell
python .\geode_graph.py --fast
```

Giữ tiến trình này chạy. Trong lần sử dụng đầu tiên, hãy đợi thông báo:

```text
Graph built and saved successfully.
```

Khi vùng lưu trữ hiện có được sử dụng lại, thông báo tương đương là:

```text
Graph loaded successfully.
```

Sau đó tiến trình hiển thị:

```text
Type your question, or 'exit' to quit.
>
```

Bạn đã có thể dùng Kwipu hoàn toàn từ terminal này: nhập câu hỏi sau dấu `>`, nhấn **Enter**, đọc câu trả lời có căn cứ rồi nhập `exit` khi hoàn tất. Ví dụ:

```text
> Who works on Project Alpha, and what are their roles?
```

Nếu chỉ cần giao diện terminal, quá trình thiết lập đã hoàn tất: bạn không cần bridge, Node.js hay frontend. Hãy giữ terminal mở nếu muốn Kwipu theo dõi thay đổi trong thư mục tài liệu.

Nếu indexer in ra `No files found. Waiting for documents...`, hãy xác nhận các tệp nằm trong `KWIPU_KNOWLEDGE_DIR` đã cấu hình.

### 7. Khởi động API bridge — Terminal 3

Để dùng giao diện trình duyệt, hãy mở một cửa sổ PowerShell khác, dán cùng khối cấu hình ở bước 5 rồi chạy:

```powershell
$env:BRIDGE_HOST = "127.0.0.1"
$env:BRIDGE_PORT = "8765"
python -m bridge
```

Giữ bridge chạy. Khởi động thành công sẽ có thông báo:

```text
Uvicorn running on http://127.0.0.1:8765
```

### 8. Kiểm tra trạng thái và khởi động frontend — Terminal 4

Từ thư mục gốc của repository:

```powershell
$health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health"
$health | ConvertTo-Json -Depth 6
```

Trước khi tiếp tục, hãy kiểm tra để chắc chắn `status`, `property_graph.status` và `ollama.status` ở cấp cao nhất đều là `ok`. Sau đó khởi động UI:

```powershell
npm --prefix .\frontend run dev
```

Mở **http://localhost:5173** trong trình duyệt. Hãy thử câu hỏi này với các tài liệu minh họa đi kèm:

> **Who works on Project Alpha, and what are their roles?**

Dùng **Ctrl+C** trong từng terminal để dừng tiến trình tương ứng. Một phiên web bình thường duy trì bốn tiến trình: Ollama (trừ khi dịch vụ desktop của nó đã chạy), terminal/indexer Kwipu, bridge và Vite.

## Sử dụng chỉ trong terminal

Terminal là một giao diện Kwipu hoàn chỉnh, không chỉ là indexer chạy nền. Nó xây dựng hoặc tải đồ thị, theo dõi tài liệu, nhận câu hỏi và in câu trả lời trực tiếp. Giao diện này cần Python và Ollama, nhưng **không** cần FastAPI, Node.js hay trình duyệt.

Sau khi hoàn tất các bước chung về mô hình và cấu hình ở trên, hãy chạy:

```powershell
.\.venv\Scripts\Activate.ps1
python .\geode_graph.py --fast
```

Sau đó đặt câu hỏi tại dấu nhắc:

```text
> What decisions were made in the January 15 meeting?
> How did Project Alpha change between the two meetings?
> Who is responsible for the API deployment?
```

Lệnh và hành vi:

- Nhập câu hỏi rồi nhấn **Enter** để truy vấn đồ thị.
- Nhập `exit`, `quit` hoặc `esci` để đóng Kwipu.
- Nhấn **Ctrl+C** để dừng.
- Để tiến trình tiếp tục chạy nhằm phát hiện tài liệu mới được tạo, sửa đổi hoặc xóa.
- Bỏ `--fast` để bật thêm trình truy xuất từ đồng nghĩa bằng LLM cho các truy vấn trong terminal.

Đối với cài đặt chỉ dùng terminal, `python -m pip install -r .\requirements.txt` là đủ. Bộ requirements rộng hơn cho bridge được dùng trong phần bắt đầu nhanh với web cũng bao gồm các dependency cốt lõi này.

## Các lệnh tương đương trên Linux và macOS

Thứ tự tiến trình vẫn giống nhau: Ollama → indexer/terminal → bridge → frontend. Thay cú pháp thiết lập và biến môi trường trên Windows bằng:

```bash
git clone https://github.com/benmaster82/Kwipu.git
cd Kwipu

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip==25.1.1
python -m pip install -r bridge/requirements.txt
npm --prefix frontend ci # web interface only

export KWIPU_ROOT_DIR="$PWD"
export KWIPU_KNOWLEDGE_DIR="knowledge_base"
export KWIPU_STORAGE_DIR="storage_graph"
export KWIPU_EMBED_MODEL="nomic-embed-text"
export KWIPU_OLLAMA_BASE_URL="http://localhost:11434"
export KWIPU_QUERY_MAX_LENGTH="4000"
export KWIPU_LLM_MODEL="gpt-oss:20b-cloud" # or qwen2.5:7b
```

Lặp lại khối `export` trong các shell của indexer và bridge, sau đó chỉ chạy những tiến trình bạn cần:

```bash
# Complete terminal interface and watcher
python geode_graph.py --fast

# Web API, in another shell
python -m bridge

# Web frontend, in another shell
npm --prefix frontend run dev
```

Cài đặt và khởi động Ollama theo hướng dẫn dành cho hệ điều hành của bạn. Trên macOS, ứng dụng Ollama có thể cung cấp dịch vụ mà không cần một terminal riêng chạy `ollama serve`.

## Sử dụng thư mục tài liệu của bạn

Bạn có thể lưu ghi chú bên ngoài repository. Hãy dùng đường dẫn nguồn tuyệt đối và một đường dẫn lưu trữ dữ liệu sinh ra riêng biệt, đồng thời lặp lại các giá trị giống nhau cho terminal/indexer, bridge và máy chủ MCP:

```powershell
$env:KWIPU_ROOT_DIR = "D:\KwipuData"
$env:KWIPU_KNOWLEDGE_DIR = "D:\Notes\MyVault"
$env:KWIPU_STORAGE_DIR = "graph-index"
$env:KWIPU_LLM_MODEL = "qwen2.5:7b"
$env:KWIPU_EMBED_MODEL = "nomic-embed-text"
python .\geode_graph.py --fast
```

Đường dẫn tương đối của tri thức và vùng lưu trữ được phân giải bên dưới `KWIPU_ROOT_DIR`. Thư mục nguồn và vùng lưu trữ được tạo ra phải tách biệt; Kwipu từ chối các bố cục lồng nhau hoặc chồng lấn để bảo vệ tài liệu nguồn.

### Cập nhật tài liệu

| Thay đổi trên hệ thống tệp | Hành động lập chỉ mục |
|---|---|
| Khởi động lần đầu khi chưa có vùng lưu trữ | Xây dựng toàn bộ |
| Chỉ có tệp mới được tạo | Chèn tăng dần |
| Có bất kỳ tệp nào được sửa đổi | Xây dựng lại toàn bộ một lần cho cả lô |
| Có bất kỳ tệp nào bị xóa | Xây dựng lại toàn bộ một lần cho cả lô |
| Sự kiện không làm thay đổi hàm băm nội dung | Bỏ qua |

Thao tác lưu nguyên tử của trình soạn thảo có thể xuất hiện dưới dạng xóa rồi tạo, vì vậy có thể kích hoạt việc xây dựng lại toàn bộ. Chỉ chạy **một** watcher CLI cốt lõi cho mỗi thư mục lưu trữ.

## Tham chiếu CLI cốt lõi

Chế độ nhanh tắt trình truy xuất từ đồng nghĩa bằng LLM cho mỗi truy vấn:

```powershell
python .\geode_graph.py --fast
```

Có thể ghi đè mô hình chỉ dành cho CLI khi sử dụng độc lập:

```powershell
python .\geode_graph.py --llm-model qwen2.5:7b --embed-model nomic-embed-text
```

Các cờ này không được truyền sang bridge hoặc máy chủ MCP. Hãy dùng biến môi trường khi nhiều thành phần chia sẻ cùng một vùng lưu trữ.

## Cách hoạt động

```text
Documents (.md/.txt/.pdf/.docx)
        │
        ▼
Structural preprocessing (wikilinks/frontmatter) + LLM path extraction
        │
        ▼
Persisted property graph and vectors (shared storage + revision manifest)
        │
        ▼
Synonym* + vector + BM25 + temporal retrieval
        │
        ▼
LLM answer with source context and citations

* Synonym retrieval is disabled in --fast mode, MCP, and bridge queries.
```

### Các thành phần

- **CLI cốt lõi** xây dựng và truy vấn đồ thị, sau đó theo dõi thư mục tri thức.
- **Máy chủ MCP** cung cấp `query_graph` và `query_graph_detailed` qua stdio MCP.
- **Bridge** cung cấp API JSON có phiên bản cho trạng thái hệ thống, ảnh chụp đồ thị, truy vấn chỉ đọc và mở rộng nguồn.
- **Frontend** hiển thị đồ thị bằng `3d-force-graph` và gọi bridge qua API base có thể cấu hình.

### Mô hình lưu trữ và tiến trình

CLI là tiến trình ghi được chỉ định. Bridge ở chế độ chỉ đọc và trả về HTTP `503` cho đến khi CLI công bố vùng lưu trữ có thể sử dụng. MCP có thể xây dựng vùng lưu trữ khi chưa tồn tại, nhưng không khởi động watcher.

Tất cả thành phần dùng chung khóa liên tiến trình và manifest phiên bản. Các truy vấn so sánh `storage_revision` và tự động tải lại thế hệ mới được commit. Các thao tác lưu bền vững chuẩn bị một thế hệ staging ngang hàng, tạm thời giữ lại thế hệ trước làm bản sao lưu rồi công bố thế hệ mới theo cách nguyên tử.

Không chạy nhiều watcher trên cùng một thư mục lưu trữ. Không xóa `storage_graph`, `.storage_graph.staging`, `.storage_graph.backup` hoặc khóa ngang hàng khi có tiến trình đang sử dụng chúng.

## Tham chiếu cấu hình

Các thiết lập được đọc khi mỗi tiến trình khởi động. Hãy khởi động lại tiến trình bị ảnh hưởng sau khi thay đổi một giá trị.

### Cấu hình cốt lõi

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `KWIPU_ROOT_DIR` | Thư mục repository | Cơ sở cho các đường dẫn dữ liệu mặc định và tương đối. |
| `KWIPU_LIVE_DIR` | — | Bí danh tương thích cho `KWIPU_ROOT_DIR`; `KWIPU_ROOT_DIR` được ưu tiên. |
| `KWIPU_KNOWLEDGE_DIR` | `knowledge_base` bên dưới thư mục gốc | Thư mục tài liệu nguồn. |
| `KWIPU_STORAGE_DIR` | `storage_graph` bên dưới thư mục gốc | Thư mục chỉ mục bền vững được tạo ra. |
| `KWIPU_LLM_MODEL` | `gpt-oss:20b-cloud` | LLM dùng để trích xuất và trả lời; mô hình mặc định có thể thực thi trên cloud. |
| `KWIPU_MODEL_NAME` | — | Bí danh tương thích cho `KWIPU_LLM_MODEL`; biến sau được ưu tiên. |
| `KWIPU_EMBED_MODEL` | `nomic-embed-text` | Mô hình embedding dùng cho các vector đã lưu. |
| `KWIPU_OLLAMA_BASE_URL` | `http://localhost:11434` | Endpoint Ollama HTTP(S) tuyệt đối. |
| `KWIPU_OLLAMA_TIMEOUT` | `300` giây | Thời gian chờ dương cho yêu cầu mô hình. |
| `KWIPU_STORAGE_LOCK_TIMEOUT` | `30` giây | Giới hạn chờ dương cho khóa lưu trữ dùng chung. |
| `KWIPU_QUERY_MAX_LENGTH` | `4000` ký tự | Độ dài tối đa của câu hỏi đã chuẩn hóa. |
| `KWIPU_MAX_SOURCE_BYTES` | `10485760` byte | Kích thước tối đa của tệp nguồn và văn bản được trích xuất khi bridge mở rộng nguồn. |
| `KWIPU_ALLOW_INSECURE_REMOTE_OLLAMA` | bị tắt | Cho phép HTTP văn bản thuần đến máy chủ không phải loopback khi được đặt thành `1`, `true`, `yes` hoặc `on`. |

Việc thay đổi mô hình embedding đòi hỏi một chỉ mục lưu trữ mới. Nếu chỉ thay đổi LLM, bạn vẫn có thể tải các vector hiện có, mặc dù lần xây dựng lại toàn bộ sau đó có thể tạo ra những quan hệ được trích xuất khác.

### Cấu hình bridge

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `BRIDGE_HOST` | `127.0.0.1` | Địa chỉ bind được `python -m bridge` sử dụng. |
| `BRIDGE_PORT` | `8765` | Cổng đã được xác thực, từ 1 đến 65535. |
| `BRIDGE_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Danh sách origin trình duyệt phân tách bằng dấu phẩy; wildcard bị từ chối. |
| `BRIDGE_ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | Các giá trị `Host` được chấp nhận; wildcard bị từ chối. |
| `BRIDGE_HEALTH_OLLAMA_TIMEOUT` | `2` giây | Thời gian chờ Ollama được `/health` sử dụng. |

Bridge cũng dùng mọi thiết lập cốt lõi ở trên. `python -m bridge` sử dụng `BRIDGE_HOST` và `BRIDGE_PORT`; khi gọi Uvicorn trực tiếp, hãy truyền chúng dưới dạng giá trị CLI:

```powershell
uvicorn bridge.app:app --reload --host $env:BRIDGE_HOST --port $env:BRIDGE_PORT
```

Xem [bridge/README.md](bridge/README.md) để biết hợp đồng API và ghi chú triển khai.

### Cấu hình frontend

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `VITE_API_BASE` | `/api` | API base của trình duyệt; giá trị tương đối sử dụng proxy Vite. |
| `VITE_BRIDGE_TARGET` | `http://127.0.0.1:8765` | Đích proxy khi phát triển. |

Với các giá trị mặc định, Vite ghi lại `/api/health` thành `/health` trên bridge. Triển khai tĩnh cho production phải cung cấp reverse proxy tương đương hoặc dùng `VITE_API_BASE` tuyệt đối; truy cập trực tiếp từ trình duyệt cũng phải khớp với `BRIDGE_CORS_ORIGINS`.

## Máy chủ MCP

Sử dụng đường dẫn tuyệt đối đến trình thông dịch Python và script trong cấu hình ứng dụng MCP. Các biến môi trường cấu hình mô hình và đường dẫn vì cờ CLI chỉ áp dụng cho `geode_graph.py`.

```json
{
  "mcpServers": {
    "kwipu": {
      "command": "C:/path/to/Kwipu/.venv/Scripts/python.exe",
      "args": ["C:/path/to/Kwipu/kwipu_mcp_server.py"],
      "env": {
        "KWIPU_KNOWLEDGE_DIR": "C:/path/to/vault",
        "KWIPU_LLM_MODEL": "qwen2.5:7b",
        "KWIPU_EMBED_MODEL": "nomic-embed-text"
      }
    }
  }
}
```

Máy chủ MCP chạy ở chế độ truy xuất nhanh và không khởi động watcher. Nó cung cấp:

- `query_graph(question)` — trả về câu trả lời dưới dạng văn bản.
- `query_graph_detailed(question)` — trả về `{"answer": "...", "citations": [...]}` với các trích dẫn được loại bỏ trùng lặp theo ID nút.

Việc chọn `gpt-oss:20b-cloud` có các hệ quả về quyền riêng tư khi dùng cloud như đã mô tả ở trên. Hãy dùng những mô hình local đã cài đặt khi cần thực thi hoàn toàn cục bộ.

## API bridge và mở rộng nguồn

Các endpoint chính của bridge gồm:

| Endpoint | Mục đích |
|---|---|
| `GET /health` | Kiểm tra vùng lưu trữ, các mô hình đã cấu hình và kết nối Ollama. |
| `GET /graph/snapshot` | Trả về đồ thị được giao diện 3D sử dụng. |
| `POST /query` | Đặt câu hỏi và nhận câu trả lời cùng trích dẫn. |
| `GET /expand?node_id=<opaque-id>` | Đọc nguồn được trích dẫn mà một nút đồ thị đại diện. |

Mở rộng nguồn đọc trực tiếp Markdown/văn bản UTF-8 và trích xuất văn bản PDF/DOCX mà không gọi LLM. Đầu vào quá lớn trả về `413`; định dạng không được hỗ trợ trả về `415`; UTF-8 không hợp lệ hoặc trích xuất cấu trúc thất bại trả về `422`; lỗi I/O nguồn tạm thời trả về `503`.

## Khắc phục sự cố

| Triệu chứng | Nội dung cần kiểm tra |
|---|---|
| Không nhận diện được `python`, `ollama`, `node` hoặc `npm` | Cài đặt điều kiện tiên quyết còn thiếu, mở terminal mới và chạy lệnh `--version` tương ứng. |
| `Activate.ps1` bị chặn | Chạy `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, sau đó kích hoạt lại môi trường. |
| `Ollama is not running` | Khởi động ứng dụng Ollama hoặc chạy `ollama serve`; xác minh `http://localhost:11434/api/tags`. |
| `Missing model(s)` | Chạy chính xác các lệnh `ollama pull <model>` mà Kwipu in ra. Đảm bảo indexer và bridge dùng cùng tên mô hình. |
| `No files found. Waiting for documents...` | Đặt các tệp được hỗ trợ trong `KWIPU_KNOWLEDGE_DIR` và xác nhận đường dẫn được in trong phần đầu của CLI. |
| Trình duyệt không mở | Giữ Vite chạy và tự mở `http://localhost:5173`. |
| Health có trạng thái `degraded` | Kiểm tra `property_graph.detail`, `ollama.detail` và danh sách `models` trong `/health`. |
| Truy vấn trả về `503` | Khởi động CLI/indexer trước và đợi xây dựng/tải đồ thị thành công. Đồng thời kiểm tra đường dẫn lưu trữ, khóa và khả năng tương thích embedding. |
| Truy vấn trả về `502` | Kiểm tra log bridge và tình trạng Ollama; query engine hoặc yêu cầu mô hình đã thất bại. Không nên dùng thao tác thử lại để che giấu một lỗi kéo dài. |
| Truy vấn trả về `400 Question is too long` | Backend báo giới hạn đang hoạt động. Mặc định là `4000`; một giá trị khác, chẳng hạn `99`, có nghĩa là `KWIPU_QUERY_MAX_LENGTH` đã bị ghi đè. Hãy đặt biến này trước khi khởi động bridge rồi khởi động lại bridge. |
| Cổng `8765` hoặc `5173` đã được sử dụng | Dừng tiến trình hiện có hoặc thay đổi nhất quán thiết lập bridge/Vite. |
| Mô hình embedding không khớp | Dừng mọi tiến trình Kwipu, khôi phục mô hình đã dùng để xây dựng vùng lưu trữ hoặc di chuyển vùng lưu trữ được tạo ra sang nơi khác rồi để CLI xây dựng lại. Tuyệt đối không xóa thư mục tài liệu nguồn. |

Kiểm tra một giá trị ghi đè trong PowerShell bằng:

```powershell
Get-ChildItem Env:KWIPU_QUERY_MAX_LENGTH
```

Đặt giá trị mặc định đã tài liệu hóa cho terminal hiện tại và khởi động lại bridge bằng:

```powershell
$env:KWIPU_QUERY_MAX_LENGTH = "4000"
python -m bridge
```

## Cấu trúc dự án

```text
Kwipu/
├── geode_graph.py                # Core engine, interactive CLI, and watcher
├── kwipu_config.py               # Canonical environment configuration
├── kwipu_storage.py              # Inter-process lock and atomic JSON helpers
├── kwipu_mcp_server.py           # MCP stdio server
├── lang_config.py                # Multilingual patterns and date/relation helpers
├── requirements.txt              # Core/terminal and MCP dependencies
├── requirements-dev.txt          # Bridge/runtime/test dependency inputs
├── requirements-dev.lock         # Hashed Python 3.12 Linux CI lock
├── requirements-dev-windows.lock # Hashed Python 3.12 Windows CI lock
├── bridge/                       # FastAPI app and read-only query adapter
├── frontend/                     # TypeScript/Vite 3D client
├── knowledge_base/examples/      # Example source documents
├── img/                          # Logo and screenshots
├── tests/                        # Standard-library unittest suite
└── storage_graph/                # Generated active index, gitignored
```

Các thư mục staging và backup ngang hàng được tạo ra cũng nằm trong gitignore và được quản lý tự động.

## Thiết lập cho nhà phát triển

Sử dụng tệp lock có băm dành riêng cho nền tảng để có môi trường bridge/runtime/test đầy đủ.

### Windows, Python 3.12

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip==25.1.1
python -m pip install --require-hashes -r .\requirements-dev-windows.lock
python -m unittest discover -s tests -p "test_*.py" -v
```

### Môi trường CI Linux, Python 3.12

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip==25.1.1
python -m pip install --require-hashes -r requirements-dev.lock
python -m unittest discover -s tests -p "test_*.py" -v
```

Các lệnh xác thực frontend là:

```powershell
npm --prefix .\frontend ci
npm --prefix .\frontend run typecheck
npm --prefix .\frontend run build
npm --prefix .\frontend audit
```

Chỉ tạo lại dependency lock từ `requirements-dev.txt` bằng quy trình được ghim đã tài liệu hóa trong [CONTRIBUTING.md](CONTRIBUTING.md), sau đó xem xét toàn bộ diff. Hãy xem hướng dẫn đó để biết mọi yêu cầu về đóng góp và xác thực.

## Giấy phép

MIT
