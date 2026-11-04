"""Desktop LOS computation isolated from the UI interpreter; Nokia stays bounded."""


def _compute(sender,start,options):
    from terrain_sites import viewshed
    try:
        import terrain_cache
        key=terrain_cache.identity(start,options);result=terrain_cache.read(key)
        if result is not None:
            sender.send(('progress',result));sender.send(('result',result));return
        result=viewshed(start,progress=lambda snapshot:sender.send(('progress',snapshot)),**options)
        terrain_cache.write(key,result)
        sender.send(('result',result))
    except Exception as error:
        # The parent closes the pipe when a newer request cancels this job.
        # A cancelled child must never print a traceback into the terminal UI.
        try:sender.send(('error',str(error)))
        except (BrokenPipeError,EOFError,OSError):pass
    finally:sender.close()


def coverage(start,*,cancelled=lambda:False,progress=None,**options):
    from desktop_elevation import enabled
    if not enabled():
        from terrain_sites import viewshed
        return viewshed(start,cancelled=cancelled,progress=progress,**options)
    if cancelled():return None
    import multiprocessing
    context=multiprocessing.get_context('spawn')
    receiver,sender=context.Pipe(duplex=False)
    process=context.Process(target=_compute,args=(sender,start,options),name='pocket-los',daemon=True)
    process.start();sender.close()
    try:
        while True:
            if cancelled():return None
            if receiver.poll(.05):
                try:kind,value=receiver.recv()
                except EOFError:raise RuntimeError('LOS worker exited without a result')
                if kind=='result':return value
                if kind=='error':raise ValueError(value)
                if progress:progress(value)
            elif not process.is_alive():raise RuntimeError('LOS worker exited without a result')
    finally:
        receiver.close()
        if process.is_alive():process.terminate()
        process.join(timeout=1)
        if process.is_alive():process.kill();process.join(timeout=1)
        process.close()
