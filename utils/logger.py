import logging

def setup_logging(log_file, prefix=None, level=logging.INFO):
    """
    配置日志记录器，使其输出到文件和控制台。
    支持一个可选的前缀，用于标识日志来源。

    每次调用都会重新配置处理器，以适应多进程环境。

    :param log_file: 日志文件的路径。
    :param prefix: (可选) 要添加到每条日志消息开头的字符串前缀。
    :param level: 日志级别。
    """
    # 使用前缀作为 logger 名称，确保每个实例有独立的 logger
    logger_name = f'app_{prefix}' if prefix else 'app_root'
    logger = logging.getLogger(logger_name) 
    logger.setLevel(level)

    # 如果该 logger 已经有 handler，说明已经配置过，直接返回
    # 这避免了重复添加 handler 导致的日志重复
    if logger.hasHandlers():
        return logger

    base_format = '%(asctime)s - %(process)d - %(levelname)s - %(message)s'

    if prefix:
        log_format = f'%(asctime)s - %(process)d - %(levelname)s - {prefix} - %(message)s'
    else:
        log_format = base_format

    fh = logging.FileHandler(log_file)
    fh.setLevel(level)

    ch = logging.StreamHandler()
    ch.setLevel(level)

    formatter = logging.Formatter(log_format)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    
    logger.propagate = False
    
    return logger