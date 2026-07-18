# Deploy no PythonAnywhere (Grátis)

## 1. Criar conta
- Acesse https://www.pythonanywhere.com/ e crie uma conta grátis

## 2. Fazer upload dos arquivos
- No dashboard, va em "Files" > "Upload a file"
- Envie todos os arquivos da pasta `server/`:
  - `main.py`
  - `wsgi.py`
  - `requirements.txt`
  - `templates/admin.html`
  - `iniciar_servidor.bat` (opcional)

## 3. Instalar dependencias
- Va em "Consoles" > "Bash"
- Execute:
  ```bash
  pip install --user -r requirements.txt
  ```

## 4. Configurar MySQL (opcional, recomendado)
- No dashboard, va em "Databases"
- Crie um banco MySQL (anote o nome, usuario e senha)
- No arquivo `wsgi.py`, altere a linha do DATABASE_URL para:
  ```python
  os.environ["DATABASE_URL"] = "mysql+pymysql://SEU_USUARIO:SUA_SENHA@SEU_HOST.mysql.pythonanywhere-services.com/SEU_USUARIO$default"
  ```

## 5. Configurar Web App
- Va em "Web" > "Add a new web app"
- Escolha "Manual configuration" > "Python 3.10"
- Em "Code":
  - "Source code": `/home/SEU_USUARIO/`
  - "Working directory": `/home/SEU_USUARIO/`
- Em "WSGI configuration file":
  - Clique no link do arquivo
  - Substitua TODO o conteudo por:
    ```python
    import sys
    sys.path.insert(0, '/home/SEU_USUARIO')
    from wsgi import application
    ```
  - Salve (Ctrl+S)
- Volte ao topo e clique "Reload"

## 6. Acessar
- URL: `https://SEU_USUARIO.pythonanywhere.com/`
- Admin: `https://SEU_USUARIO.pythonanywhere.com/admin`
- Login: `admin` / `admin`

## 7. Atualizar o app Android
- No arquivo `SessionManager.kt`, troque a URL para:
  ```
  https://SEU_USUARIO.pythonanywhere.com/
  ```
- Recompile o APK
