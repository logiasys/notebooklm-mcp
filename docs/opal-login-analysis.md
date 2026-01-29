# Análisis de sesión, mantenimiento y comunicación (base NotebookLM)

Este documento describe **cómo este repositorio obtiene y mantiene una sesión** (Google/NotebookLM), la **estructura de comunicación** entre componentes y **cómo replicar la funcionalidad de login** para un flujo tipo “Opal de Google”. El objetivo es dejar una guía técnica reutilizable para implementar un login persistente y las acciones operativas sobre un servicio web similar.

## 1) Cómo se obtiene la sesión (paso a paso)

### 1.1 Configuración de autenticación
- La configuración vive en `AuthConfig` y se carga desde `notebooklm-config.json` o variables de entorno. La opción crítica es `use_persistent_session`, que habilita un **perfil de Chrome persistente**. Esto permite reutilizar cookies, tokens y almacenamiento local entre ejecuciones. 【F:src/notebooklm_mcp/config.py†L15-L37】

### 1.2 Inicialización del navegador
- El cliente `NotebookLMClient` inicia el navegador en `start()` y crea el **perfil persistente** en `profile_dir` cuando está habilitado. Para “anti-detection” usa `undetected-chromedriver` si está disponible; de lo contrario usa Selenium con flags anti-automatización. 【F:src/notebooklm_mcp/client.py†L34-L96】
- En modo **headless** se añaden opciones de Chrome específicas para ejecución sin UI. 【F:src/notebooklm_mcp/client.py†L34-L96】

### 1.3 Navegación y detección de login
- `authenticate()` navega a `base_url` o `base_url/notebook/<id>`.
- Luego evalúa `current_url` para detectar si redirigió a `accounts.google.com` o `signin`. Si **no** redirige, considera sesión autenticada; si **redirige**, se requiere login manual (en modo no headless). 【F:src/notebooklm_mcp/client.py†L103-L142】

### 1.4 Resultado y estado interno
- El cliente mantiene `self._is_authenticated` como bandera de sesión activa. Esto se usa por la capa de servidor para reportar el estado en `healthcheck` y para permitir operaciones como `send_message`. 【F:src/notebooklm_mcp/client.py†L38-L42】【F:src/notebooklm_mcp/server.py†L74-L113】

## 2) Cómo se mantiene la sesión

### 2.1 Persistencia de credenciales
- Al activar `use_persistent_session`, se guarda el perfil en `profile_dir`, lo cual conserva cookies, tokens y sesión de Google. 【F:src/notebooklm_mcp/config.py†L15-L37】【F:src/notebooklm_mcp/client.py†L44-L56】

### 2.2 Reautenticación automática
- En ejecuciones posteriores, el flujo vuelve a visitar el mismo `base_url`; si la sesión persiste, no redirige al login y se marca como autenticado automáticamente. 【F:src/notebooklm_mcp/client.py†L123-L142】

### 2.3 Manejo operativo desde CLI
- El CLI guía al usuario para realizar el login manual una única vez, y luego valida la sesión para futuras ejecuciones. Esto evita pedir credenciales en cada ejecución. 【F:src/notebooklm_mcp/cli.py†L458-L507】

## 3) Estructura de comunicación

### 3.1 Flujo lógico
1. **CLI** inicia el servidor o comandos de chat.
2. **Server (FastMCP)** crea el cliente y expone herramientas (`send_chat_message`, `navigate_to_notebook`, etc.).
3. **Client** ejecuta Selenium, autentica sesión y manipula la UI web.
4. **NotebookLM** responde en la UI, que se lee/parsa con Selenium.

Este flujo se ve en la estructura de servidor y en las herramientas expuestas por FastMCP. 【F:src/notebooklm_mcp/server.py†L28-L156】

### 3.2 Diagrama resumido
```
CLI -> FastMCP Server -> NotebookLMClient (Selenium/Chrome) -> NotebookLM Web UI
```

## 4) Implementación inicial para “Opal de Google”

> Nota: el objetivo es crear un flujo **análogo** al de NotebookLM, **sin asumir** detalles internos de Opal. La implementación actual es una base configurable que usa selectores CSS para detectar listas, botones y resultados.

### 4.1 Módulo de autenticación equivalente
- Se agregó `OpalClient`, con la misma estrategia de perfil persistente y validación por redirección de URL (detecta `signin`/`accounts.google.com`). 【F:src/notebooklm_mcp/opal_client.py†L1-L146】
- El cliente mantiene `_is_authenticated` y expone operaciones para listar opals, iniciar procesos y leer resultados. 【F:src/notebooklm_mcp/opal_client.py†L148-L271】

### 4.2 Configuración para Opal
- La configuración vive en `OpalConfig` (habilitado, URLs y selectores CSS), disponible en `ServerConfig` y en el JSON generado por el CLI. 【F:src/notebooklm_mcp/config.py†L26-L71】【F:src/notebooklm_mcp/cli.py†L54-L83】
- Las variables de entorno permiten ajustar URLs y selectores sin recompilar. 【F:src/notebooklm_mcp/config.py†L86-L133】

### 4.3 Login simultáneo (NotebookLM + Opal)
- El flujo de `guided_setup` ahora también valida sesión en Opal cuando la integración está habilitada. 【F:src/notebooklm_mcp/cli.py†L704-L804】

## 5) Acciones operativas disponibles para Opal

La integración expone herramientas MCP dedicadas para Opal:

1. **opal_authenticate**: valida/crea sesión de Opal.
2. **opal_list**: lista opals disponibles.
3. **opal_process**: inicia el procesamiento de un opal.
4. **opal_result**: obtiene el resultado de un opal.
5. **opal_actions**: lista acciones disponibles en un opal.

Estas acciones están disponibles en el servidor FastMCP v2 y reutilizan el mismo perfil de autenticación. 【F:src/notebooklm_mcp/server.py†L74-L246】

## 6) Recomendaciones de seguridad y estabilidad

- **Evitar extraer credenciales**: usar el navegador para el login interactivo y preservar la sesión.
- **Separar perfiles por entorno**: evitar compartir `profile_dir` entre entornos de distinta seguridad.
- **Rotación de sesión**: agregar `logout()` y limpieza del perfil cuando sea necesario.
- **Observabilidad**: instrumentar métricas (auth failures, sesiones activas) para monitoreo. 【F:src/notebooklm_mcp/monitoring.py†L33-L128】

---

### Resumen
Este repositorio usa un patrón consistente de **navegador persistente + detección de redirecciones** para login, y expone la sesión vía `_is_authenticated`. Esta misma estructura puede replicarse para Opal creando un cliente con lógica equivalente y exponer herramientas MCP para autenticar, navegar y operar acciones clave.
