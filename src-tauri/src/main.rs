#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{sync::Mutex,process::{Child,Command,Stdio},net::{TcpListener,TcpStream},time::Duration,io::{Read,Write}};
use tauri::Manager;
struct Backend(Mutex<Option<Child>>);
fn main() {
 let app=tauri::Builder::default().manage(Backend(Mutex::new(None))).setup(|app| {
    let socket=TcpListener::bind("127.0.0.1:0")?;
    let port=socket.local_addr()?.port();drop(socket);
    let token=uuid::Uuid::new_v4().to_string();
    let exe=std::env::current_exe()?.parent().unwrap().join(if cfg!(windows) {"stageos-backend.exe"} else {"stageos-backend"});
    let mut cmd=Command::new(exe);
    cmd.args(["--port",&port.to_string()]).env("STAGEOS_TOKEN",&token).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)] {use std::os::windows::process::CommandExt;cmd.creation_flags(0x08000000);}
    let mut child=cmd.spawn()?;
    let mut ready=false;
    for _ in 0..240 {
        if let Some(status)=child.try_wait()? {return Err(format!("StageOS backend exited: {status}").into());}
        if let Ok(mut stream)=TcpStream::connect_timeout(&format!("127.0.0.1:{port}").parse()?,Duration::from_millis(200)) {
            stream.set_read_timeout(Some(Duration::from_millis(500)))?;
            let request=format!("GET /api/auth/theatres HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-StageOS-Token: {token}\r\nConnection: close\r\n\r\n");
            let _=stream.write_all(request.as_bytes());let mut buf=[0;128];
            if let Ok(n)=stream.read(&mut buf) {if String::from_utf8_lossy(&buf[..n]).contains("200 OK") {ready=true;break;}}
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    if !ready {let _=child.kill();return Err("StageOS backend timeout".into());}
    *app.state::<Backend>().0.lock().unwrap()=Some(child);
    tauri::WebviewWindowBuilder::new(app,"main",tauri::WebviewUrl::External(format!("http://127.0.0.1:{port}/?token={token}").parse()?)).title("StageOS — управление театральным производством").inner_size(1440.0,940.0).min_inner_size(1000.0,700.0).build()?;
    Ok(())
 }).build(tauri::generate_context!()).expect("StageOS could not start");
 app.run(|handle,event| {
    if let tauri::RunEvent::Exit=event {if let Some(mut child)=handle.state::<Backend>().0.lock().unwrap().take(){let _=child.kill();let _=child.wait();}}
 });
}
