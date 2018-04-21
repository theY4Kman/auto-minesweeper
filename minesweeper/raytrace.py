def int_trace(x0, y0, x1, y1):
    """Yield all integer coords between two points

    Source: http://playtechs.blogspot.com/2007/03/raytracing-on-grid.html
    """
    d_x, d_y = abs(x1 - x0), abs(y1 - y0)
    n = 1 + d_x + d_y
    error = d_x - d_y

    x, y = x0, y0
    inc_x, inc_y = (1 if d_x > 0 else -1), (1 if d_y > 0 else -1)
    d_x, d_y = (d_x * 2), (d_y * 2)
    for _ in range(n):
        yield x, y

        if error > 0:
            x += inc_x
            error -= d_y
        else:
            y += inc_y
            error += d_x
