# Auditoría de seguridad y análisis funcional

## Alcance y metodología

Esta auditoría se basa en el análisis estático del código fuente y la documentación incluida en el repositorio. Se revisan: flujo de autenticación, almacenamiento de perfiles/cookies, transporte MCP, logging, y superficies de ataque típicas (inyección de prompts, exfiltración de datos y controles de acceso). El objetivo es identificar riesgos, sesgos de seguridad y controles existentes, además de documentar **todas** las funciones y opciones del sistema.

## Resumen de hallazgos de seguridad

### 1) Persistencia de sesión y manejo de perfiles (riesgo de exposición de credenciales)
- El servidor utiliza un perfil de Chrome persistente (`auth.profile_dir`) para conservar la sesión de Google y permitir ejecución headless sin re-login. Esto implica que cookies y tokens quedan almacenados en disco, y el perfil puede exportarse/importarse con utilidades de CLI. La exposición de ese directorio equivale a compartir credenciales de sesión. Ver configuración y utilidades de import/export en `config.py` y `cli.py`.【F:src/notebooklm_mcp/config.py†L14-L182】【F:src/notebooklm_mcp/cli.py†L536-L642】
- El flujo de configuración por defecto crea `chrome_profile_notebooklm` y habilita `use_persistent_session`, lo que refuerza la necesidad de proteger permisos de filesystem y evitar copias no autorizadas.【F:src/notebooklm_mcp/cli.py†L32-L69】【F:src/notebooklm_mcp/client.py†L45-L72】

**Sesgo de seguridad:** prioriza la continuidad de la sesión y experiencia de usuario (persistencia) por encima de un modelo de autenticación más efímero, lo que aumenta el riesgo si el perfil es filtrado.

### 2) Ausencia de control de acceso/Autenticación para transporte HTTP/SSE
- El servidor FastMCP puede exponerse por HTTP o SSE, pero no implementa autenticación, autorización ni restricciones de origen. Cualquier cliente que pueda acceder al endpoint puede invocar herramientas MCP. La guía HTTP menciona explícitamente que se debe agregar autenticación en producción, pero el código no lo implementa. Esto incrementa el riesgo de uso indebido y abuso remoto del navegador automatizado. Revisar `server.py` y la guía HTTP.【F:src/notebooklm_mcp/server.py†L240-L270】【F:docs/http-server-guide.md†L240-L276】

**Sesgo de seguridad:** el diseño asume un entorno confiable o “local-only”, lo que no es seguro si se expone el puerto a redes compartidas.

### 3) Logging de mensajes y posible exposición de datos sensibles
- El servidor registra con `loguru` eventos de envío de mensajes, incluyendo los primeros 50 caracteres del prompt (`request.message[:50]`). Esto puede filtrar datos sensibles si el prompt contiene información privada. Además, el logging persistente escribe a archivos locales (`logs/notebooklm-mcp.log`, `logs/notebooklm-mcp-errors.log`) sin redacción de datos. Revisar `server.py` y `monitoring.py`.【F:src/notebooklm_mcp/server.py†L116-L137】【F:src/notebooklm_mcp/monitoring.py†L260-L307】

**Sesgo de seguridad:** prioriza la trazabilidad y diagnósticos sobre la minimización de datos sensibles en logs.

### 4) Riesgo de inyección de prompts (prompt injection)
- Los mensajes enviados al modelo se transmiten tal cual a NotebookLM sin filtrado ni validación adicional. Un actor puede introducir instrucciones maliciosas en el prompt si el sistema recibe entradas de usuarios no confiables, afectando la salida del modelo o induciendo comportamientos no deseados. El diseño asume que la entrada del usuario es confiable. Ver envío de mensajes en `server.py` y `client.py`.【F:src/notebooklm_mcp/server.py†L116-L162】【F:src/notebooklm_mcp/client.py†L147-L203】

**Sesgo de seguridad:** el flujo es “prompt-forwarding” directo, sin defensas contra instrucciones adversarias.

### 5) Obtención de respuestas con scraping del DOM
- El cliente extrae la respuesta con selectores CSS y “fallbacks” amplios (`p, div, span`), lo que podría capturar contenido no deseado (p.ej., texto de UI o información residual del navegador). Esto es un riesgo menor pero puede producir “copias accidentales” de contenido adicional. Revisar `_get_current_response` en `client.py`.【F:src/notebooklm_mcp/client.py†L239-L337】

### 6) Operaciones de filesystem peligrosas (import/export de perfiles)
- Los comandos `import-profile` y `export-profile` utilizan `copytree` y `rmtree` sobre rutas proporcionadas por el usuario, sin validaciones adicionales. Un operador podría borrar datos accidentalmente o copiar perfiles a rutas inseguras si pasa paths incorrectos. Ver `cli.py` y `config.py`.【F:src/notebooklm_mcp/cli.py†L536-L642】【F:src/notebooklm_mcp/config.py†L144-L182】

### 7) Exfiltración hacia terceros (NotebookLM)
- Toda interacción (prompt y respuesta) se realiza vía navegador y se envía a NotebookLM; por definición, la información se transmite a un servicio de terceros (Google). No hay cifrado adicional ni control interno sobre el contenido enviado. Este es un riesgo inherente al diseño. Ver uso de Selenium y navegación a la URL de NotebookLM en `client.py`.【F:src/notebooklm_mcp/client.py†L112-L201】【F:src/notebooklm_mcp/client.py†L418-L452】

## Controles y mitigaciones existentes
- Validación de configuración: límites de timeout, checks de ruta para perfiles, y validación de importación de perfiles. Esto reduce fallos de ejecución, pero no mitiga exposición de credenciales una vez en disco.【F:src/notebooklm_mcp/config.py†L110-L142】
- Modo headless opcional, y autenticación manual cuando se detecta “signin” en la URL. Esto evita intentar usar sesión no autenticada. Ver `_authenticate_sync`.【F:src/notebooklm_mcp/client.py†L112-L145】
- Registro de estado de autenticación en herramientas y healthcheck, útil para detectar fallos de login. Ver `healthcheck` en `server.py`.【F:src/notebooklm_mcp/server.py†L83-L115】

## Recomendaciones (prioridad alta → media)
1. **Agregar autenticación al transporte HTTP/SSE** (p. ej., token compartido, mTLS, o reverse proxy con auth).【F:src/notebooklm_mcp/server.py†L240-L270】【F:docs/http-server-guide.md†L240-L276】
2. **Redactar/limitar logging de prompts** o habilitar un modo “no log prompts” por configuración. Revisar el logging actual de mensajes. 【F:src/notebooklm_mcp/server.py†L116-L137】【F:src/notebooklm_mcp/monitoring.py†L260-L307】
3. **Seguridad del perfil**: documentar cifrado de disco, permisos restrictivos y evitar compartir perfiles por canales inseguros. Revisar uso del directorio persistente. 【F:src/notebooklm_mcp/config.py†L14-L182】【F:src/notebooklm_mcp/client.py†L45-L72】
4. **Validación de entradas para prompt injection**: si se usa con inputs externos, aplicar sanitización o guardrails antes de enviar a NotebookLM. Ver funciones de envío de mensajes. 【F:src/notebooklm_mcp/server.py†L116-L162】【F:src/notebooklm_mcp/client.py†L147-L203】
5. **Reducir alcance del scraping**: restringir selectores a elementos de respuesta para minimizar capturas accidentales. Ver `_get_current_response`. 【F:src/notebooklm_mcp/client.py†L239-L337】

---

## Inventario de funciones, herramientas y opciones

### Herramientas MCP (FastMCP v2)
Definidas en `server.py`:
- `healthcheck()`: devuelve estado, autenticación, notebook y modo.【F:src/notebooklm_mcp/server.py†L83-L115】
- `send_chat_message(request)`: envía mensaje y opcionalmente espera respuesta.【F:src/notebooklm_mcp/server.py†L116-L137】
- `get_chat_response(request)`: recupera respuesta con timeout (lógica interna usa `get_response`).【F:src/notebooklm_mcp/server.py†L140-L162】
- `get_quick_response()`: respuesta inmediata sin espera explícita adicional.【F:src/notebooklm_mcp/server.py†L164-L180】
- `chat_with_notebook(request)`: flujo completo con cambio de notebook opcional, envío y lectura de respuesta.【F:src/notebooklm_mcp/server.py†L182-L212】
- `navigate_to_notebook(request)`: navegación explícita a notebook ID.【F:src/notebooklm_mcp/server.py†L214-L236】
- `get_default_notebook()`: notebook por defecto actual.【F:src/notebooklm_mcp/server.py†L238-L246】
- `set_default_notebook(request)`: actualiza notebook por defecto.【F:src/notebooklm_mcp/server.py†L248-L270】

### Cliente de automatización (`NotebookLMClient`)
Funciones principales en `client.py`:
- `start()` / `_start_browser()`: inicia navegador con Chrome o undetected-chromedriver.【F:src/notebooklm_mcp/client.py†L40-L90】
- `_start_regular_chrome()`: fallback con Selenium estándar y opciones anti-detección.【F:src/notebooklm_mcp/client.py†L92-L127】
- `authenticate()` / `_authenticate_sync()`: valida sesión, detecta login requerido, marca `_is_authenticated`.【F:src/notebooklm_mcp/client.py†L103-L145】
- `send_message()` / `_send_message_sync()`: ubica input de chat y envía prompt.【F:src/notebooklm_mcp/client.py†L147-L205】
- `get_response()` / `_wait_for_streaming_response()` / `_get_current_response()`: espera respuesta y extrae texto del DOM.【F:src/notebooklm_mcp/client.py†L206-L337】
- `_check_streaming_indicators()` y `_clean_response_text()`: heurísticas para detectar streaming y limpiar respuesta.【F:src/notebooklm_mcp/client.py†L213-L415】
- `navigate_to_notebook()` / `_navigate_to_notebook_sync()`: navegación explícita por ID.【F:src/notebooklm_mcp/client.py†L418-L452】
- `close()`: cierra navegador y limpia sesión local.【F:src/notebooklm_mcp/client.py†L454-L476】

### CLI (comandos y opciones)
Comandos definidos en `cli.py`:
- `init NOTEBOOK_URL`: genera config, crea perfil y guía autenticación inicial.【F:src/notebooklm_mcp/cli.py†L104-L198】
- `server`: opciones `--notebook`, `--headless`, `--port`, `--host`, `--root-dir`, `--transport` (stdio/http/sse).【F:src/notebooklm_mcp/cli.py†L205-L309】
- `chat`: modo interactivo o mensaje único con `--notebook`, `--message`, `--headless`.【F:src/notebooklm_mcp/cli.py†L312-L381】
- `quick-setup`: crea config con `--config`, `--notebook`, `--profile`, `--headless`, `--setup-only`.【F:src/notebooklm_mcp/cli.py†L384-L529】
- `import-profile`: copia perfil desde `--from-profile` a `--to-profile`.【F:src/notebooklm_mcp/cli.py†L532-L590】
- `export-profile`: exporta perfil con `--profile` (opcional) y `--to`.【F:src/notebooklm_mcp/cli.py†L593-L642】
- `config-show`: imprime la configuración actual como tabla.【F:src/notebooklm_mcp/cli.py†L645-L670】
- `test`: prueba de navegador, auth y navegación con `--notebook`, `--headless`.【F:src/notebooklm_mcp/cli.py†L673-L731】

### Configuración y opciones principales
En `config.py`:
- **ServerConfig**: `headless`, `timeout`, `debug`, `default_notebook_id`, `base_url`, `server_name`, `stdio_mode`, `streaming_timeout`, `response_stability_checks`, `retry_attempts`.【F:src/notebooklm_mcp/config.py†L32-L58】
- **AuthConfig**: `cookies_path`, `profile_dir`, `use_persistent_session`, `auto_login`, `import_profile_from`, `export_profile_to`, `skip_manual_login`.【F:src/notebooklm_mcp/config.py†L14-L30】
- Métodos: `from_file`, `from_env`, `validate`, `setup_profile`, `export_profile`, `save_to_file`.【F:src/notebooklm_mcp/config.py†L60-L182】

### Observabilidad
- `monitoring.py` contiene `MetricsCollector`, `HealthChecker`, métricas Prometheus opcionales, y logging estructurado a archivos locales. Esto impacta seguridad por persistencia de logs. 【F:src/notebooklm_mcp/monitoring.py†L14-L307】
