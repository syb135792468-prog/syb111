# Python标准库教程完整文档
> 本文档完整保留了原教程的所有内容，仅对格式进行规范化调整，适配数据库导入需求，无内容删减与篡改。

---

## 1. 基础标准模块（续）
### 1.15 time 模块
time模块提供了一系列处理时间的函数，时间值可以是**从1970年1月1日0点（Unix纪元）到现在经过的秒数（Unix格式）**，也可以是表示时间的struct类元组。

#### 1.15.1 获得当前时间
Example 1-79 展示了如何使用 time 模块获取当前时间。

**Example 1-79. 使用 time 模块获取当前时间**
File: time-example-1.py
```python
import time

now = time.time()
print now, "seconds since", time.gmtime(0)[:6]
print
print "or in other words:"
print "- local time:", time.localtime(now)
print "- utc:", time.gmtime(now)
```
**输出结果**
```
937758359.77 seconds since (1970, 1, 1, 0, 0, 0)

or in other words:
- local time: (1999, 9, 19, 18, 25, 59, 6, 262, 1)
- utc: (1999, 9, 19, 16, 25, 59, 6, 262, 0)
```

`localtime` 和 `gmtime` 返回的类元组包含字段：年、月、日、时、分、秒、星期、一年中的第几天、夏令时标志。其中年是四位数，星期从星期一（数字0代表）开始，1月1日是一年的第一天。

#### 1.15.2 将时间值转换为字符串
你可以使用标准的格式化字符串把时间对象转换为字符串，time模块也提供了许多标准转换函数，如Example 1-80所示。

**Example 1-80. 使用 time 模块格式化时间输出**
File: time-example-2.py
```python
import time

now = time.localtime(time.time())
print time.asctime(now)
print time.strftime("%y/%m/%d %H:%M", now)
print time.strftime("%a %b %d", now)
print time.strftime("%c", now)
print time.strftime("%I %p", now)
print time.strftime("%Y-%m-%d %H:%M:%S %Z", now)

# do it by hand...
year, month, day, hour, minute, second, weekday, yearday, daylight = now
print "%04d-%02d-%02d" % (year, month, day)
print "%02d:%02d:%02d" % (hour, minute, second)
print ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")[weekday], yearday
```
**输出结果**
```
Sun Oct 10 21:39:24 1999
99/10/10 21:39
Sun Oct 10
Sun Oct 10 21:39:24 1999
09 PM
1999-10-10 21:39:24 CEST
1999-10-10
21:39:24
SUN 283
```

#### 1.15.3 将字符串转换为时间对象
在一些平台上，time模块包含了`strptime`函数，它的作用与`strftime`相反。给定一个字符串和模式，它返回相应的时间对象，如Example 1-81所示。

**Example 1-81. 使用 time.strptime 函数解析时间**
File: time-example-6.py
```python
import time

# make sure we have a strptime function!
# 确认有函数 strptime
try:
    strptime = time.strptime
except AttributeError:
    from strptime import strptime

print strptime("31 Nov 00", "%d %b %y")
print strptime("1 Jan 70 1:30pm", "%d %b %y %I:%M%p")
```

只有在系统的 C 库提供了相应的函数的时候，`time.strptime`函数才可以使用。对于没有提供标准实现的平台，Example 1-82提供了一个不完全的实现。

**Example 1-82. strptime 实现**
File: strptime.py
```python
import re
import string

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

SPEC = {
    # map formatting code to a regular expression fragment
    "%a": "(?P<weekday>[a-z]+)",
    "%A": "(?P<weekday>[a-z]+)",
    "%b": "(?P<month>[a-z]+)",
    "%B": "(?P<month>[a-z]+)",
    "%C": "(?P<century>\d\d?)",
    "%d": "(?P<day>\d\d?)",
    "%D": "(?P<month>\d\d?)/(?P<day>\d\d?)/(?P<year>\d\d)",
    "%e": "(?P<day>\d\d?)",
    "%h": "(?P<month>[a-z]+)",
    "%H": "(?P<hour>\d\d?)",
    "%I": "(?P<hour12>\d\d?)",
    "%j": "(?P<yearday>\d\d?\d?)",
    "%m": "(?P<month>\d\d?)",
    "%M": "(?P<minute>\d\d?)",
    "%R": "(?P<hour>\d\d?):(?P<minute>\d\d?)",
    "%p": "(?P<ampm12>am|pm)",
    "%S": "(?P<second>\d\d?)",
    "%w": "(?P<weekday>\d)",
    "%T": "(?P<hour>\d\d?):(?P<minute>\d\d?):(?P<second>\d\d?)",
    "%U": "(?P<week>\d\d)",
    "%W": "(?P<weekday>\d\d)",
    "%y": "(?P<year>\d\d)",
    "%Y": "(?P<year>\d\d\d\d)",
    "%%": "%"
}

class TimeParser:
    def __init__(self, format):
        # convert strptime format string to regular expression
        format = string.join(re.split("(?:\s|%t|%n)+", format))
        pattern = []
        try:
            for spec in re.findall("%\w|%%|.", format):
                if spec[0] == "%":
                    spec = SPEC[spec]
                pattern.append(spec)
        except KeyError:
            raise ValueError, "unknown specificer: %s" % spec
        self.pattern = re.compile("(?i)" + string.join(pattern, ""))

    def match(self, daytime):
        # match time string
        match = self.pattern.match(daytime)
        if not match:
            raise ValueError, "format mismatch"
        get = match.groupdict().get
        tm = [0]*9

        # extract date elements
        y = get("year")
        if y:
            y = int(y)
            if y < 68:
                y = 2000 + y
            elif y < 100:
                y = 1900 + y
            tm[0] = y
        m = get("month")
        if m:
            if m in MONTHS:
                m = MONTHS.index(m) + 1
            tm[1] = int(m)
        d = get("day")
        if d:
            tm[2] = int(d)

        # extract time elements
        h = get("hour")
        if h:
            tm[3] = int(h)
        else:
            h = get("hour12")
            if h:
                h = int(h)
                if string.lower(get("ampm12", "")) == "pm":
                    h = h + 12
                tm[3] = h
        m = get("minute")
        if m:
            tm[4] = int(m)
        s = get("second")
        if s:
            tm[5] = int(s)

        # ignore weekday/yearday for now
        return tuple(tm)

def strptime(string, format="%a %b %d %H:%M:%S %Y"):
    return TimeParser(format).match(string)

if __name__ == "__main__":
    # try it out
    import time
    print strptime("2000-12-20 01:02:03", "%Y-%m-%d %H:%M:%S")
    print strptime(time.ctime(time.time()))
```
**输出结果**
```
(2000, 11, 15, 12, 30, 45, 0, 0, 0)
(2000, 12, 20, 1, 2, 3, 0, 0, 0)
```

#### 1.15.4 转换时间值
将时间元组转换回时间值非常简单，至少我们谈论的当地时间 (local time) 如此。只要把时间元组传递给`mktime`函数，如Example 1-83所示。

**Example 1-83. 使用 time 模块将本地时间元组转换为时间值(整数)**
File: time-example-3.py
```python
import time

t0 = time.time()
tm = time.localtime(t0)
print tm
print t0
print time.mktime(tm)
```
**输出结果**
```
(1999, 9, 9, 0, 11, 8, 3, 252, 1)
936828668.16
936828668.0
```

但是，1.5.2版本的标准库没有提供能将UTC时间（世界标准时间）转换为时间值的函数（Python和对应底层C库都没有提供）。Example 1-84提供了该函数的一个Python实现，称为`timegm`。

**Example 1-84. 将 UTC 时间元组转换为时间值(整数)**
File: time-example-4.py
```python
import time

def _d(y, m, d, days=(0,31,59,90,120,151,181,212,243,273,304,334,365)):
    # map a date to the number of days from a reference point
    return (((y - 1901)*1461)/4 + days[m-1] + d +
        ((m > 2 and not y % 4 and (y % 100 or not y % 400)) and 1))

def timegm(tm, epoch=_d(1970,1,1)):
    year, month, day, h, m, s = tm[:6]
    assert year >= 1970
    assert 1 <= month <= 12
    return (_d(year, month, day) - epoch)*86400 + h*3600 + m*60 + s

t0 = time.time()
tm = time.gmtime(t0)
print tm
print t0
print timegm(tm)
```
**输出结果**
```
(1999, 9, 8, 22, 12, 12, 2, 251, 0)
936828732.48
936828732
```

从1.6版本开始，calendar模块提供了一个类似的函数`calendar.timegm`。

#### 1.15.5 Timing 相关
time模块可以计算Python程序的执行时间，如Example 1-85所示。你可以测量 "wall time" (真实世界时间)，或是"进程时间" (消耗的CPU时间)。

**Example 1-85. 使用 time 模块评价算法**
File: time-example-5.py
```python
import time

def procedure():
    time.sleep(2.5)

# measure process time
t0 = time.clock()
procedure()
print time.clock() - t0, "seconds process time"

# measure wall time
t0 = time.time()
procedure()
print time.time() - t0, "seconds wall time"
```
**输出结果**
```
0.0 seconds process time
2.50903499126 seconds wall time
```

> 注意：并不是所有的系统都能测量真实的进程时间。一些系统中(包括 Windows)，clock函数通常测量从程序启动到测量时的wall time。进程时间的精度受限制，在一些系统中，它超过30分钟后进程会被清理。

---

### 1.16 types 模块
types模块包含了标准解释器定义的所有类型的类型对象，同一类型的所有对象共享一个类型对象。你可以使用`is`来检查一个对象是不是属于某个给定类型，如Example 1-86所示。

**Example 1-86. 使用 types 模块**
File: types-example-1.py
```python
import types

def check(object):
    print object,

    if type(object) is types.IntType:
        print "INTEGER",
    if type(object) is types.FloatType:
        print "FLOAT",
    if type(object) is types.StringType:
        print "STRING",
    if type(object) is types.ClassType:
        print "CLASS",
    if type(object) is types.InstanceType:
        print "INSTANCE",
    print

check(0)
check(0.0)
check("0")

class A:
    pass

class B:
    pass

check(A)
check(B)

a = A()
b = B()

check(a)
check(b)
```
**输出结果**
```
0 INTEGER
0.0 FLOAT
0 STRING
A CLASS
B CLASS
<A instance at 796960> INSTANCE
<B instance at 796990> INSTANCE
```

注意：所有的类都具有相同的类型，所有的实例也是一样。要测试一个类或者实例所属的类，可以使用内建的`issubclass`和`isinstance`函数。

> 警告：types模块在第一次引入的时候会破坏当前的异常状态。也就是说，不要在异常处理语句块中导入该模块 (或其他会导入它的模块)。

---

### 1.17 gc 模块
(可选, 2.0及以后版本) gc模块提供了到内建循环垃圾收集器的接口。

Python使用引用记数来跟踪什么时候销毁一个对象；一个对象的最后一个引用一旦消失，这个对象就会被销毁。从2.0版开始，Python还提供了一个循环垃圾收集器，它每隔一段时间执行，用来查找指向自身的数据结构，并尝试破坏循环，如Example 1-87所示。

你可以使用`gc.collect`函数来强制完整收集，这个函数将返回收集器销毁的对象的数量。

**Example 1-87. 使用 gc 模块收集循环引用垃圾**
File: gc-example-1.py
```python
import gc

# create a simple object that links to itself
class Node:
    def __init__(self, name):
        self.name = name
        self.parent = None
        self.children = []

    def addchild(self, node):
        node.parent = self
        self.children.append(node)

    def __repr__(self):
        return "<Node %s at %x>" % (repr(self.name), id(self))

# set up a self-referencing structure
root = Node("monty")
root.addchild(Node("eric"))
root.addchild(Node("john"))
root.addchild(Node("michael"))

# remove our only reference
del root

print gc.collect(), "unreachable objects"
print gc.collect(), "unreachable objects"
```
**输出结果**
```
12 unreachable objects
0 unreachable objects
```

如果你确定你的程序不会创建自引用的数据结构，你可以使用`gc.disable`函数禁用垃圾收集，调用这个函数以后，Python的工作方式将与1.5.2或更早的版本相同。

---

## 2. 更多标准模块
> 引言："Now, imagine that your friend kept complaining that she didn't want to visit you since she found it too hard to climb up the drain pipe, and you kept telling her to use the friggin' stairs like everyone else..."
> — eff-bot, June 1998

### 2.1 概览
本章叙述了许多在Python程序中广泛使用的模块，使用它们可以大幅节省开发时间。

#### 2.1.1 文件与流
- `fileinput`模块：可以让你更简单地向不同的文件写入内容，提供了简单的封装类，通过for-in语句即可循环得到一个或多个文本文件的内容。
- `StringIO`模块（及`cStringIO`变种）：实现了工作在内存的文件对象，在大多需要标准文件对象的地方都可以替换使用。

#### 2.1.2 类型封装
`UserDict`、`UserList`、`UserString`是对应内建类型的顶层简单封装。和内建类型不同的是，这些封装是可以被继承的，在需要一个和内建类型行为相似但有额外新方法的类时非常有用。

#### 2.1.3 随机数字
`random`模块提供了一些不同的随机数字生成器；`whrandom`模块与此相似，但允许你创建多个生成器对象（注：whrandom在版本2.1时声明不支持，推荐使用random替代）。

#### 2.1.4 加密算法
- `md5`和`sha`模块：用于计算密写的信息标记（cryptographically strong message signatures，即信息摘要）。
- `crypt`模块：实现了DES样式的单向加密，只在Unix系统下可用。
- `rotor`模块：提供了简单的双向加密，版本2.3时申明不支持，因为它的加密运算不安全。

---

### 2.2 fileinput 模块
fileinput模块允许你循环一个或多个文本文件的内容，如Example 2-1所示。

**Example 2-1. 使用 fileinput 模块循环一个文本文件**
File: fileinput-example-1.py
```python
import fileinput
import sys

for line in fileinput.input("samples/sample.txt"):
    sys.stdout.write("-> ")
    sys.stdout.write(line)
```
**输出结果**
```
-> We will perhaps eventually be writing only small
-> modules which are identified by name as they are
-> used to build larger ones, so that devices like
-> indentation, rather than delimiters, might become
-> feasible for expressing local structure in the
-> source language.
-> -- Donald E. Knuth, December 1974
```

你也可以使用fileinput模块获得当前行的元信息 (meta information)，其中包括`isfirstline`、`filename`、`lineno`，如Example 2-2所示。

**Example 2-2. 使用 fileinput 模块处理多个文本文件**
File: fileinput-example-2.py
```python
import fileinput
import glob
import string, sys

for line in fileinput.input(glob.glob("samples/*.txt")):
    if fileinput.isfirstline(): # first in a file?
        sys.stderr.write("-- reading %s --\n" % fileinput.filename())
        sys.stdout.write(str(fileinput.lineno()) + " " + string.upper(line))
    else:
        sys.stdout.write(line)
```
**输出结果**
```
-- reading samples\sample.txt --
1 WE WILL PERHAPS EVENTUALLY BE WRITING ONLY SMALL
2 MODULES WHICH ARE IDENTIFIED BY NAME AS THEY ARE
3 USED TO BUILD LARGER ONES, SO THAT DEVICES LIKE
4 INDENTATION, RATHER THAN DELIMITERS, MIGHT BECOME
5 FEASIBLE FOR EXPRESSING LOCAL STRUCTURE IN THE
6 SOURCE LANGUAGE.
7 -- DONALD E. KNUTH, DECEMBER 1974
```

文本文件的替换操作非常简单，只需要把`inplace`关键字参数设置为1，传递给`input`函数，该模块会自动完成相关处理，Example 2-3展示了这些。

**Example 2-3. 使用 fileinput 模块将 CRLF 改为 LF**
File: fileinput-example-3.py
```python
import fileinput, sys

for line in fileinput.input(inplace=1):
    # convert Windows/DOS text files to Unix files
    if line[-2:] == "\r\n":
        line = line[:-2] + "\n"
    sys.stdout.write(line)
```

---

### 2.3 shutil 模块
shutil实用模块包含了一些用于复制文件和文件夹的函数。Example 2-4中使用的`copy`函数使用和Unix下`cp`命令基本相同的方式复制一个文件。

**Example 2-4. 使用 shutil 复制文件**
File: shutil-example-1.py
```python
import shutil
import os

for file in os.listdir("."):
    if os.path.splitext(file)[1] == ".py":
        print file
        shutil.copy(file, os.path.join("backup", file))
```
**输出结果**
```
aifc-example-1.py
anydbm-example-1.py
array-example-1.py
...
```

`copytree`函数用于复制整个目录树 (与`cp -r`相同)，而`rmtree`函数用于删除整个目录树 (与`rm -r`相同)，如Example 2-5所示。

**Example 2-5. 使用 shutil 模块复制/删除目录树**
File: shutil-example-2.py
```python
import shutil
import os

SOURCE = "samples"
BACKUP = "samples-bak"

# create a backup directory
shutil.copytree(SOURCE, BACKUP)
print os.listdir(BACKUP)

# remove it
shutil.rmtree(BACKUP)
print os.listdir(BACKUP)
```
**输出结果**
```
['sample.wav', 'sample.jpg', 'sample.au', 'sample.msg', 'sample.tgz',
...
Traceback (most recent call last):
  File "shutil-example-2.py", line 17, in ?
    print os.listdir(BACKUP)
os.error: No such file or directory
```

---

### 2.4 tempfile 模块
Example 2-6中展示的tempfile模块允许你快速地创建名称唯一的临时文件供使用。

**Example 2-6. 使用 tempfile 模块创建临时文件**
File: tempfile-example-1.py
```python
import tempfile
import os

tempfile = tempfile.mktemp()
print "tempfile", "=>", tempfile

file = open(tempfile, "w+b")
file.write("*" * 1000)
file.seek(0)
print len(file.read()), "bytes"
file.close()

try:
    os.remove(tempfile)
except OSError:
    pass
```
**输出结果**
```
tempfile => C:\TEMP\~160-1
1000 bytes
```

`TemporaryFile`函数会自动挑选合适的文件名，并打开文件，如Example 2-7所示。而且它会确保该文件在关闭的时候会被自动删除。(在Unix下，你可以删除一个已打开的文件，这时文件关闭时它会被自动删除。在其他平台上，这通过一个特殊的封装类实现。)

**Example 2-7. 使用 tempfile 模块打开临时文件**
File: tempfile-example-2.py
```python
import tempfile

file = tempfile.TemporaryFile()
for i in range(100):
    file.write("*" * 100)
file.close() # removes the file!
```

---

### 2.5 StringIO 模块
Example 2-8展示了StringIO模块的使用，它实现了一个工作在内存的文件对象 (内存文件)。在大多需要标准文件对象的地方都可以使用它来替换。

**Example 2-8. 使用 StringIO 模块从内存文件读入内容**
File: stringio-example-1.py
```python
import StringIO

MESSAGE = "That man is depriving a village somewhere of a computer scientist."

file = StringIO.StringIO(MESSAGE)
print file.read()
```
**输出结果**
```
That man is depriving a village somewhere of a computer scientist.
```

StringIO类实现了内建文件对象的所有方法，此外还有`getvalue`方法用来返回它内部的字符串值，Example 2-9展示了这个方法。

**Example 2-9. 使用 StringIO 模块向内存文件写入内容**
File: stringio-example-2.py
```python
import StringIO

file = StringIO.StringIO()
file.write("This man is no ordinary man. ")
file.write("This is Mr. F. G. Superman.")

print file.getvalue()
```
**输出结果**
```
This man is no ordinary man. This is Mr. F. G. Superman.
```

StringIO可以用于重新定向Python解释器的输出，如Example 2-10所示。

**Example 2-10. 使用 StringIO 模块捕获输出**
File: stringio-example-3.py
```python
import StringIO
import string, sys

stdout = sys.stdout
sys.stdout = file = StringIO.StringIO()

print """
According to Gbaya folktales, trickery and guile
are the best ways to defeat the python, king of
snakes, which was hatched from a dragon at the
world's start. -- National Geographic, May 1997
"""

sys.stdout = stdout
print string.upper(file.getvalue())
```
**输出结果**
```
ACCORDING TO GBAYA FOLKTALES, TRICKERY AND GUILE
ARE THE BEST WAYS TO DEFEAT THE PYTHON, KING OF
SNAKES, WHICH WAS HATCHED FROM A DRAGON AT THE
WORLD'S START. -- NATIONAL GEOGRAPHIC, MAY 1997
```

---

### 2.6 cStringIO 模块
cStringIO是一个可选的模块，是StringIO的更快速实现。它的工作方式和StringIO基本相同，但是它不可以被继承，Example 2-11展示了cStringIO的用法。

**Example 2-11. 使用 cStringIO 模块**
File: cstringio-example-1.py
```python
import cStringIO

MESSAGE = "That man is depriving a village somewhere of a computer scientist."

file = cStringIO.StringIO(MESSAGE)
print file.read()
```
**输出结果**
```
That man is depriving a village somewhere of a computer scientist.
```

为了让你的代码尽可能快，同时保证兼容低版本的Python，你可以使用一个小技巧在cStringIO不可用时启用StringIO模块，如Example 2-12所示。

**Example 2-12. 后退至 StringIO**
File: cstringio-example-2.py
```python
try:
    import cStringIO
    StringIO = cStringIO
except ImportError:
    import StringIO

print StringIO
```
**输出结果**
```
<module 'StringIO' (built-in)>
```

---

### 2.7 mmap 模块
(2.0新增) mmap模块提供了操作系统内存映射函数的接口，映射区域的行为和字符串对象类似，但数据是直接从文件读取的，如Example 2-13所示。

**Example 2-13. 使用 mmap 模块**
File: mmap-example-1.py
```python
import mmap
import os

filename = "samples/sample.txt"

file = open(filename, "r+")
size = os.path.getsize(filename)

data = mmap.mmap(file.fileno(), size)

# basics
print data
print len(data), size

# use slicing to read from the file
# 使用切片操作读取文件
print repr(data[:10]), repr(data[:10])

# or use the standard file interface
# 或使用标准的文件接口
print repr(data.read(10)), repr(data.read(10))
```
**输出结果**
```
<mmap object at 008A2A10>
302 302
'We will pe' 'We will pe'
'We will pe' 'rhaps even'
```

> 注意：在Windows下，这个文件必须以既可读又可写的模式打开(`r+`、`w+`、或`a+`)，否则mmap调用会失败。

Example 2-14展示了内存映射区域的使用，在很多地方它都可以替换普通字符串使用，包括正则表达式和其他字符串操作。

**Example 2-14. 对映射区域使用字符串方法和正则表达式**
File: mmap-example-2.py
```python
import mmap
import os, string, re

def mapfile(filename):
    file = open(filename, "r+")
    size = os.path.getsize(filename)
    return mmap.mmap(file.fileno(), size)

data = mapfile("samples/sample.txt")

# search
index = data.find("small")
print index, repr(data[index-5:index+15])

# regular expressions work too!
m = re.search("small", data)
print m.start(), m.group()
```
**输出结果**
```
43 'only small\015\012modules '
43 small
```

---

### 2.8 UserDict 模块
UserDict模块包含了一个可继承的字典类（事实上是对内建字典类型的Python封装）。Example 2-15展示了一个增强的字典类，允许对字典使用 "加/+" 操作并提供了接受关键字参数的构造函数。

**Example 2-15. 使用 UserDict 模块**
File: userdict-example-1.py
```python
import UserDict

class FancyDict(UserDict.UserDict):
    def __init__(self, data = {}, **kw):
        UserDict.UserDict.__init__(self)
        self.update(data)
        self.update(kw)

    def __add__(self, other):
        dict = FancyDict(self.data)
        dict.update(other)
        return dict

a = FancyDict(a = 1)
b = FancyDict(b = 2)
print a + b
```
**输出结果**
```
{'b': 2, 'a': 1}
```

---

### 2.9 UserList 模块
UserList模块包含了一个可继承的列表类（事实上是对内建列表类型的Python封装）。在Example 2-16中，AutoList实例类似一个普通的列表对象，但它允许你通过赋值为列表添加项目。

**Example 2-16. 使用 UserList 模块**
File: userlist-example-1.py
```python
import UserList

class AutoList(UserList.UserList):
    def __setitem__(self, i, item):
        if i == len(self.data):
            self.data.append(item)
        else:
            self.data[i] = item

list = AutoList()
for i in range(10):
    list[i] = i

print list
```
**输出结果**
```
[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
```

---

### 2.10 UserString 模块
(2.0新增) UserString模块包含两个类，`UserString`和`MutableString`。前者是对标准字符串类型的封装，后者是一个变种，允许你修改特定位置的字符。

> 注意：MutableString并不是效率很好，许多操作是通过切片和字符串连接实现的。如果性能对你的脚本来说很重要，你最好使用字符串片断的列表或者array模块。

**Example 2-17. 使用 UserString 模块**
File: userstring-example-1.py
```python
import UserString

class MyString(UserString.MutableString):
    def append(self, s):
        self.data = self.data + s

    def insert(self, index, s):
        self.data = self.data[:index] + s + self.data[index:]

    def remove(self, s):
        self.data = self.data.replace(s, "")

file = open("samples/book.txt")
text = file.read()
file.close()

book = MyString(text)

for bird in ["gannet", "robin", "nuthatch"]:
    book.remove(bird)

print book
```
**输出结果**
```
C: The one without the !
P: The one without the -!!! They've ALL got the !! It's a Standard
British Bird, the , it's in all the books!!!
```

---

### 2.11 traceback 模块
traceback模块允许你在程序里打印异常的跟踪返回 (Traceback)信息，类似未捕获异常时解释器所做的，如Example 2-18所示。

> 注意：导入traceback模块会清理掉异常状态，所以最好别在异常处理代码中导入该模块。

**Example 2-18. 使用 traceback 模块打印跟踪返回信息**
File: traceback-example-1.py
```python
# note! importing the traceback module messes up the
# exception state, so you better do that here and not
# in the exception handler
# 注意! 导入 traceback 会清理掉异常状态, 所以
# 最好别在异常处理代码中导入该模块
import traceback

try:
    raise SyntaxError, "example"
except:
    traceback.print_exc()
```
**输出结果**
```
Traceback (innermost last):
  File "traceback-example-1.py", line 7, in ?
    raise SyntaxError, "example"
SyntaxError: example
```

Example 2-19使用StringIO模块将跟踪返回信息放在字符串中。

**Example 2-19. 使用 traceback 模块将跟踪返回信息复制到字符串**
File: traceback-example-2.py
```python
import traceback
import StringIO

try:
    raise IOError, "an i/o error occurred"
except:
    fp = StringIO.StringIO()
    traceback.print_exc(file=fp)
    message = fp.getvalue()

    print "failure! the error was:", repr(message)
```
**输出结果**
```
failure! the error was: 'Traceback (innermost last):\012  File "traceback-example-2.py", line 5, in ?\012IOError: an i/o error occurred\012'
```

你可以使用`extract_tb`函数格式化跟踪返回信息，得到包含错误信息的列表，如Example 2-20所示。

**Example 2-20. 使用 traceback Module 模块编码 Traceback 对象**
File: traceback-example-3.py
```python
import traceback
import sys

def function():
    raise IOError, "an i/o error occurred"

try:
    function()
except:
    info = sys.exc_info()
    for file, lineno, function, text in traceback.extract_tb(info[2]):
        print file, "line", lineno, "in", function
        print "=>", repr(text)
    print "** %s: %s" % info[:2]
```
**输出结果**
```
traceback-example-3.py line 8 in ?
=> 'function()'
traceback-example-3.py line 5 in function
=> 'raise IOError, "an i/o error occurred"'
** exceptions.IOError: an i/o error occurred
```

---

### 2.12 errno 模块
errno模块定义了许多的符号错误码，比如`ENOENT` ("没有该目录入口") 以及`EPERM` ("权限被拒绝")。它还提供了一个映射到对应平台数字错误代码的字典。

在大多情况下，`IOError`异常会提供一个二元元组，包含对应数值错误代码和一个说明字符串。如果你需要区分不同的错误代码，那么最好在可能的地方使用符号名称。

**Example 2-21. 使用 errno 模块**
File: errno-example-1.py
```python
import errno

try:
    fp = open("no.such.file")
except IOError, (error, message):
    if error == errno.ENOENT:
        print "no such file"
    elif error == errno.EPERM:
        print "permission denied"
    else:
        print message
```
**输出结果**
```
no such file
```

Example 2-22展示了如何使用`errorcode`字典把数字错误码映射到符号名称。

**Example 2-22. 使用 errorcode 字典**
File: errno-example-2.py
```python
import errno

try:
    fp = open("no.such.file")
except IOError, (error, message):
    print error, repr(message)
    print errno.errorcode[error]
```
**输出结果**
```
2 'No such file or directory'
ENOENT
```

---

### 2.13 getopt 模块
getopt模块包含用于抽出命令行选项和参数的函数，它可以处理多种格式的选项。其中第2个参数指定了允许的可缩写的选项，选项名后的冒号(:) 意味这这个选项必须有额外的参数。

**Example 2-23. 使用 getopt 模块**
File: getopt-example-1.py
```python
import getopt
import sys

# simulate command-line invocation
# 模仿命令行参数
sys.argv = ["myscript.py", "-l", "-d", "directory", "filename"]

# process options
# 处理选项
opts, args = getopt.getopt(sys.argv[1:], "ld:")

long = 0
directory = None

for o, v in opts:
    if o == "-l":
        long = 1
    elif o == "-d":
        directory = v

print "long", "=", long
print "directory", "=", directory
print "arguments", "=", args
```
**输出结果**
```
long = 1
directory = directory
arguments = ['filename']
```

为了让getopt查找长的选项，传递一个描述选项的列表做为第3个参数。如果一个选项名称以等号(=) 结尾，那么它必须有一个附加参数。

**Example 2-24. 使用 getopt 模块处理长选项**
File: getopt-example-2.py
```python
import getopt
import sys

# simulate command-line invocation
# 模仿命令行参数
sys.argv = ["myscript.py", "--echo", "--printer", "lp01", "message"]

opts, args = getopt.getopt(sys.argv[1:], "ep:", ["echo", "printer="])

# process options
# 处理选项
echo = 0
printer = None

for o, v in opts:
    if o in ("-e", "--echo"):
        echo = 1
    elif o in ("-p", "--printer"):
        printer = v

print "echo", "=", echo
print "printer", "=", printer
print "arguments", "=", args
```
**输出结果**
```
echo = 1
printer = lp01
arguments = ['message']
```

---

### 2.14 getpass 模块
getpass模块提供了平台无关的在命令行下输入密码的方法。
- `getpass(prompt)`：会显示提示字符串，关闭键盘的屏幕反馈，然后读取密码。如果提示参数省略，那么它将打印出 "Password: "。
- `getuser()`：获得当前用户名，如果可能的话。

**Example 2-25. 使用 getpass 模块**
File: getpass-example-1.py
```python
import getpass

usr = getpass.getuser()
pwd = getpass.getpass("enter password for user %s: " % usr)
print usr, pwd
```
**输出结果**
```
enter password for user mulder:
mulder trustno1
```

---

### 2.15 glob 模块
glob根据给定模式生成满足该模式的文件名列表，和Unix shell相同。
- 模式语法：星号(`*`) 匹配零个或更多个字符，问号(`?`) 匹配单个字符。也可以使用方括号来指定字符范围，例如`[0-9]`代表一个数字，其他所有字符都代表它们本身。
- `glob(pattern)`：返回满足给定模式的所有文件的列表。

**Example 2-26. 使用 glob 模块**
File: glob-example-1.py
```python
import glob

for file in glob.glob("samples/*.jpg"):
    print file
```
**输出结果**
```
samples/sample.jpg
```

> 注意：这里的glob返回完整路径名，这点和`os.listdir`函数不同。glob事实上使用了`fnmatch`模块来完成模式匹配。

---

### 2.16 fnmatch 模块
fnmatch模块使用模式来匹配文件名，模式语法和Unix shell中所使用的相同。
- 星号(`*`) 匹配零个或更多个字符，问号(`?`) 匹配单个字符。
- 可以使用方括号来指定字符范围，例如`[0-9]`代表一个数字。
- 其他所有字符都匹配它们本身。

**Example 2-27. 使用 fnmatch 模块匹配文件**
File: fnmatch-example-1.py
```python
import fnmatch
import os

for file in os.listdir("samples"):
    if fnmatch.fnmatch(file, "*.jpg"):
        print file
```
**输出结果**
```
sample.jpg
```

Example 2-28中的`translate`函数可以将一个文件匹配模式转换为正则表达式。

**Example 2-28. 使用 fnmatch 模块将模式转换为正则表达式**
File: fnmatch-example-2.py
```python
import fnmatch
import os, re

pattern = fnmatch.translate("*.jpg")

for file in os.listdir("samples"):
    if re.match(pattern, file):
        print file

print "(pattern was %s)" % pattern
```
**输出结果**
```
sample.jpg
(pattern was .*\.jpg$)
```

glob和find模块在内部使用fnmatch模块来实现。

---

### 2.17 random 模块
> 引言："Anyone who considers arithmetical methods of producing random digits is, of course, in a state of sin."
> — John von Neumann, 1951

random模块包含许多随机数生成器，基本随机数生成器基于Wichmann和Hill (1982)的数学运算理论。

**Example 2-29. 使用 random 模块获得随机数字**
File: random-example-1.py
```python
import random

for i in range(5):
    # random float: 0.0 <= number < 1.0
    print random.random(),
    # random float: 10 <= number < 20
    print random.uniform(10, 20),
    # random integer: 100 <= number <= 1000
    print random.randint(100, 1000),
    # random integer: even numbers in 100 <= number < 1000
    print random.randrange(100, 1000, 2)
```
**输出结果**
```
0.946842713956 19.5910069381 709 172
0.573613195398 16.2758417025 407 120
0.363241598013 16.8079747714 916 580
0.602115173978 18.386796935 531 774
0.526767588533 18.0783794596 223 344
```

> 注意：`randint`函数可以返回上界，而其他函数总是返回小于上界的值，所有函数都有可能返回下界值。

Example 2-30展示了`choice`函数，它用来从一个序列里分拣出一个随机项目，可用于列表、元组、以及其他非空序列。

**Example 2-30. 使用 random 模块从序列取出随机项**
File: random-example-2.py
```python
import random

# random choice from a list
for i in range(5):
    print random.choice([1, 2, 3, 5, 9])
```
**输出结果**
```
2
3
1
9
1
```

在2.0及以后版本，`shuffle`函数可以用于打乱一个列表的内容 (也就是生成一个该列表的随机全排列)。Example 2-31展示了如何在旧版本中实现该函数。

**Example 2-31. 使用 random 模块打乱一副牌**
File: random-example-4.py
```python
import random

try:
    # available in 2.0 and later
    shuffle = random.shuffle
except AttributeError:
    def shuffle(x):
        for i in xrange(len(x)-1, 0, -1):
            # pick an element in x[:i+1] with which to exchange x[i]
            j = int(random.random() * (i+1))
            x[i], x[j] = x[j], x[i]

cards = range(52)
shuffle(cards)
myhand = cards[:5]
print myhand
```
**输出结果**
```
[4, 8, 40, 12, 30]
```

random模块也包含了非恒定分布的随机生成器函数。Example 2-32使用了`gauss` (高斯)函数来生成满足高斯分布的随机数字。

**Example 2-32. 使用 random 模块生成高斯分布随机数**
File: random-example-3.py
```python
import random

histogram = [0] * 20

# calculate histogram for gaussian
# noise, using average=5, stddev=1
for i in range(1000):
    i = int(random.gauss(5, 1) * 2)
    histogram[i] = histogram[i] + 1

# print the histogram
m = max(histogram)
for v in histogram:
    print "*" * (v * 50 / m)
```
**输出结果**
```
****
**********
*************************
***********************************
************************************************
**************************************************
*************************************
***************************
*************
***
*
```

> 注意：标准库中提供的随机数生成器都是伪随机数生成器，对于模拟、数值分析、游戏等场景足够使用，但不适合密码学用途。

---

### 2.18 whrandom 模块
这个模块早在2.1就被声明不赞成使用，推荐使用random模块代替。

whrandom模块提供了一个伪随机数生成器 (基于Wichmann和Hill, 1982的数学运算理论)。除非你需要不共享状态的多个生成器(如多线程程序)，否则请使用random模块代替。

**Example 2-33. 使用 whrandom 模块**
File: whrandom-example-1.py
```python
import whrandom

# same as random
print whrandom.random()
print whrandom.choice([1, 2, 3, 5, 9])
print whrandom.uniform(10, 20)
print whrandom.randint(100, 1000)
```
**输出结果**
```
0.113412062346
1
16.8778954689
799
```

Example 2-34展示了如何使用whrandom类实例创建多个生成器。

**Example 2-34. 使用 whrandom 模块创建多个随机生成器**
File: whrandom-example-2.py
```python
import whrandom

# initialize all generators with the same seed
rand1 = whrandom.whrandom(4,7,11)
rand2 = whrandom.whrandom(4,7,11)
rand3 = whrandom.whrandom(4,7,11)

for i in range(5):
    print rand1.random(), rand2.random(), rand3.random()
```
**输出结果**
```
0.123993532536 0.123993532536 0.123993532536
0.180951499518 0.180951499518 0.180951499518
0.291924111809 0.291924111809 0.291924111809
0.952048889363 0.952048889363 0.952048889363
0.969794283643 0.969794283643 0.969794283643
```

---

### 2.19 md5 模块
md5 (Message-Digest Algorithm 5)模块用于计算信息密文(信息摘要)。md5算法计算一个强壮的128位密文，这意味着如果两个字符串是不同的，那么有极高可能它们的md5也不同。也就是说，给定一个md5密文，那么几乎没有可能再找到另个字符串的密文与此相同。

**Example 2-35. 使用 md5 模块**
File: md5-example-1.py
```python
import md5

hash = md5.new()
hash.update("spam, spam, and eggs")

print repr(hash.digest())
```
**输出结果**
```
'L\005J\243\266\355\243u`\305r\203\267\020F\303'
```

Example 2-36展示了如何获得一个十六进制或base64编码的字符串。

**Example 2-36. 使用 md5 模块获得十六进制或 base64 编码的 md5 值**
File: md5-example-2.py
```python
import md5
import string
import base64

hash = md5.new()
hash.update("spam, spam, and eggs")

value = hash.digest()
print hash.hexdigest()

# before 2.0, the above can be written as
# 在 2.0 前, 以上应该写做:
# print string.join(map(lambda v: "%02x" % ord(v), value), "")

print base64.encodestring(value)
```
**输出结果**
```
4c054aa3b6eda37560c57283b71046c3
TAVKo7bto3VgxXKDtxBGww==
```

Example 2-37展示了如何使用md5校验和来处理口令的发送与应答的验证。

**Example 2-37. 使用 md5 模块来处理口令的发送与应答的验证**
File: md5-example-3.py
```python
import md5
import string, random

def getchallenge():
    # generate a 16-byte long random string. (note that the built-
    # in pseudo-random generator uses a 24-bit seed, so this is not
    # as good as it may seem...)
    # 生成一个 16 字节长的随机字符串. 注意内建的伪随机生成器
    # 使用的是 24 位的种子(seed), 所以这里这样用并不好..
    challenge = map(lambda i: chr(random.randint(0, 255)), range(16))
    return string.join(challenge, "")

def getresponse(password, challenge):
    # calculate combined digest for password and challenge
    # 计算密码和质询(challenge)的联合密文
    m = md5.new()
    m.update(password)
    m.update(challenge)
    return m.digest()

#
# server/client communication
# 服务器/客户端通讯

# 1. client connects. server issues challenge.
# 1. 客户端连接, 服务器发布质询(challenge)
print "client:", "connect"

challenge = getchallenge()
print "server:", repr(challenge)

# 2. client combines password and challenge, and calculates
# the response.
# 2. 客户端计算密码和质询(challenge)的组合后的密文
client_response = getresponse("trustno1", challenge)
print "client:", repr(client_response)

# 3. server does the same, and compares the result with the
# client response. the result is a safe login in which the
# password is never sent across the communication channel.
# 3. 服务器做同样的事, 然后比较结果与客户端的返回,
# 判断是否允许用户登陆. 这样做密码没有在通讯中明文传输.
server_response = getresponse("trustno1", challenge)

if server_response == client_response:
    print "server:", "login ok"
```
**输出结果**
```
client: connect
server: '\334\352\227Z#\272\273\212KG\330\265\032>\311o'
client: "l'\305\240-x\245\237\035\225A\254\233\337\225\001"
server: login ok
```

Example 2-38提供了md5的一个变种，你可以通过标记信息来判断它是否在网络传输过程中被修改(丢失)。

**Example 2-38. 使用 md5 模块检查数据完整性**
File: md5-example-4.py
```python
import md5
import array

class HMAC_MD5:
    # keyed md5 message authentication
    def __init__(self, key):
        opad = array.array("B", [0x5C] * 64)
        ipad = array.array("B", [0x36] * 64)
        if len(key) > 64:
            key = md5.new(key).digest()
        for i in range(len(key)):
            ipad[i] = ipad[i] ^ ord(key[i])
            opad[i] = opad[i] ^ ord(key[i])
        self.ipad = md5.md5(ipad.tostring())
        self.opad = md5.md5(opad.tostring())

    def digest(self, data):
        ipad = self.ipad.copy()
        opad = self.opad.copy()
        ipad.update(data)
        opad.update(ipad.digest())
        return opad.digest()

#
# simulate server end
# 模拟服务器端
key = "this should be a well-kept secret"
message = open("samples/sample.txt").read()
signature = HMAC_MD5(key).digest(message)

# (send message and signature across a public network)
# (经过由网络发送信息和签名)

#
# simulate client end
#模拟客户端
key = "this should be a well-kept secret"

client_signature = HMAC_MD5(key).digest(message)

if client_signature == signature:
    print "this is the original message:"
    print
    print message
else:
    print "someone has modified the message!!!"
```

> 注意：`copy`方法会对这个内部对象状态做一个快照( snapshot )，这允许你预先计算部分密文摘要。该算法的细节请参阅 HMAC-MD5:Keyed-MD5 for Message Authentication。
> 警告：千万别忘记内建的伪随机生成器对于加密操作而言并不合适，千万小心。

---

### 2.20 sha 模块
sha模块提供了计算信息摘要(密文)的另种方法，它与md5模块类似，但生成的是160位签名。

**Example 2-39. 使用 sha 模块**
File: sha-example-1.py
```python
import sha

hash = sha.new()
hash.update("spam, spam, and eggs")

print repr(hash.digest())
print hash.hexdigest()
```
**输出结果**
```
'\321\333\003\026I\331\272-j\303\247\240\345\343Tvq\364\346\311'
d1db031649d9ba2d6ac3a7a0e5e3547671f4e6c9
```

关于sha密文的使用，请参阅md5中的例子。

---

### 2.21 crypt 模块
(可选, 只用于Unix) crypt模块实现了单向的DES加密，Unix系统使用这个加密算法来储存密码，这个模块真正也就只在检查这样的密码时有用。

Example 2-40展示了如何使用`crypt.crypt`来加密一个密码，将密码和salt组合起来然后传递给函数，这里的salt包含两位随机字符。加密后你可以扔掉原密码而只保存加密后的字符串。

**Example 2-40. 使用 crypt 模块**
File: crypt-example-1.py
```python
import crypt
import random, string

def getsalt(chars = string.letters + string.digits):
    # generate a random 2-character 'salt'
    # 生成随机的 2 字符 'salt'
    return random.choice(chars) + random.choice(chars)

print crypt.crypt("bananas", getsalt())
```
**输出结果**
```
'py8UGrijma1j6'
```

确认密码时，只需要用新密码调用加密函数，并取加密后字符串的前两位作为salt即可。如果结果和加密后字符串匹配，那么密码就是正确的。Example 2-41使用pwd模块来获取已知用户的加密后密码。

**Example 2-41. 使用 crypt 模块身份验证**
File: crypt-example-2.py
```python
import pwd, crypt

def login(user, password):
    "Check if user would be able to log in using password"
    try:
        pw1 = pwd.getpwnam(user)[1]
        pw2 = crypt.crypt(password, pw1[:2])
        return pw1 == pw2
    except KeyError:
        return 0 # no such user

user = raw_input("username:")
password = raw_input("password:")

if login(user, password):
    print "welcome", user
else:
    print "login failed"
```

关于其他实现验证的方法请参阅md5模块一节。

---

### 2.22 rotor 模块
这个模块在2.3时被声明不赞成，2.4时废弃，因为它的加密算法不安全。

(可选) rotor模块实现了一个简单的加密算法，它的算法基于WWII Enigma engine。

**Example 2-42. 使用 rotor 模块**
File: rotor-example-1.py
```python
import rotor

SECRET_KEY = "spam"
MESSAGE = "the holy grail"

r = rotor.newrotor(SECRET_KEY)

encoded_message = r.encrypt(MESSAGE)
decoded_message = r.decrypt(encoded_message)

print "original:", repr(MESSAGE)
print "encoded message:", repr(encoded_message)
print "decoded message:", repr(decoded_message)
```
**输出结果**
```
original: 'the holy grail'
encoded message: '\227\271\244\015\305sw\3340\337\252\237\340U'
decoded message: 'the holy grail'
```

---

### 2.23 zlib 模块
(可选) zlib模块为 "zlib" 压缩提供支持 (这种压缩方法是 "deflate")。

Example 2-43展示了如何使用`compress`和`decompress`函数接受字符串参数。

**Example 2-43. 使用 zlib 模块压缩字符串**
File: zlib-example-1.py
```python
import zlib

MESSAGE = "life of brian"

compressed_message = zlib.compress(MESSAGE)
decompressed_message = zlib.decompress(compressed_message)

print "original:", repr(MESSAGE)
print "compressed message:", repr(compressed_message)
print "decompressed message:", repr(decompressed_message)
```
**输出结果**
```
original: 'life of brian'
compressed message: 'x\234\313\311LKU\310OSH*\312L\314\003\000!\010\004\302'
decompressed message: 'life of brian'
```

文件的内容决定了压缩比率，Example 2-44说明了这点。

**Example 2-44. 使用 zlib 模块压缩多个不同类型文件**
File: zlib-example-2.py
```python
import zlib
import glob

for file in glob.glob("samples/*"):
    indata = open(file, "rb").read()
    outdata = zlib.compress(indata, zlib.Z_BEST_COMPRESSION)
    print file, len(indata), "=>", len(outdata),
    print "%d%%" % (len(outdata) * 100 / len(indata))
```
**输出结果**
```
samples\sample.au 1676 => 1109 66%
samples\sample.gz 42 => 51 121%
samples\sample.htm 186 => 135 72%
samples\sample.jpg 4762 => 4632 97%
samples\sample.msg 450 => 275 61%
samples\sample.sgm 430 => 321 74%
samples\sample.tar 10240 => 125 1%
samples\sample.tgz 155 => 159 102%
samples\sample.txt 302 => 220 72%
samples\sample.wav 13260 => 10992 82%
samples\sample.ini 246 => 190 77%
```

你也可以实时地压缩或解压缩数据，如Example 2-45所示。

**Example 2-45. 使用 zlib 模块解压缩流**
File: zlib-example-3.py
```python
import zlib

encoder = zlib.compressobj()

data = encoder.compress("life")
data = data + encoder.compress(" of ")
data = data + encoder.compress("brian")
data = data + encoder.flush()

print repr(data)
print repr(zlib.decompress(data))
```
**输出结果**
```
'x\234\313\311LKU\310OSH*\312L\314\003\000!\010\004\302'
'life of brian'
```

Example 2-46把解码对象封装到了一个类似文件对象的类中，实现了一些文件对象的方法，这样使得读取压缩文件更方便。

**Example 2-46. 压缩流的仿文件访问方式**
File: zlib-example-4.py
```python
import zlib
import string, StringIO

class ZipInputStream:
    def __init__(self, file):
        self.file = file
        self.__rewind()

    def __rewind(self):
        self.zip = zlib.decompressobj()
        self.pos = 0 # position in zipped stream
        self.offset = 0 # position in unzipped stream
        self.data = ""

    def __fill(self, bytes):
        if self.zip:
            # read until we have enough bytes in the buffer
            while not bytes or len(self.data) < bytes:
                self.file.seek(self.pos)
                data = self.file.read(16384)
                if not data:
                    self.data = self.data + self.zip.flush()
                    self.zip = None # no more data
                    break
                self.pos = self.pos + len(data)
                self.data = self.data + self.zip.decompress(data)

    def seek(self, offset, whence=0):
        if whence == 0:
            position = offset
        elif whence == 1:
            position = self.offset + offset
        else:
            raise IOError, "Illegal argument"
        if position < self.offset:
            raise IOError, "Cannot seek backwards"

        # skip forward, in 16k blocks
        while position > self.offset:
            if not self.read(min(position - self.offset, 16384)):
                break

    def tell(self):
        return self.offset

    def read(self, bytes = 0):
        self.__fill(bytes)
        if bytes:
            data = self.data[:bytes]
            self.data = self.data[bytes:]
        else:
            data = self.data
            self.data = ""
        self.offset = self.offset + len(data)
        return data

    def readline(self):
        # make sure we have an entire line
        while self.zip and "\n" not in self.data:
            self.__fill(len(self.data) + 512)
        i = string.find(self.data, "\n") + 1
        if i <= 0:
            return self.read()
        return self.read(i)

    def readlines(self):
        lines = []
        while 1:
            s = self.readline()
            if not s:
                break
            lines.append(s)
        return lines

#
# try it out
data = open("samples/sample.txt").read()
data = zlib.compress(data)
file = ZipInputStream(StringIO.StringIO(data))
for line in file.readlines():
    print line[:-1]
```
**输出结果**
```
We will perhaps eventually be writing only small
modules which are identified by name as they are
used to build larger ones, so that devices like
indentation, rather than delimiters, might become
feasible for expressing local structure in the
source language.
-- Donald E. Knuth, December 1974
```

---

### 2.24 code 模块
code模块提供了一些用于模拟标准交互解释器行为的函数。

`compile_command`与内建`compile`函数行为相似，但它会通过测试来保证你传递的是一个完成的Python语句。在Example 2-47中，我们一行一行地编译一个程序，编译完成后会执行所得到的代码对象 (code object)。

**Example 2-47. 使用 code 模块编译语句**
File: code-example-1.py
```python
import code
import string, sys

SCRIPT = [
    "a = (",
    "1, 2,",
    "3",
    ")",
    "print a"
]

script = ""
for line in SCRIPT:
    script = script + line + "\n"
    co = code.compile_command(script, "<stdin>", "exec")
    if co:
        # got a complete statement. execute it!
        print "-"*40
        print script,
        print "-"*40
        exec co
        script = ""
```
**输出结果**
```
----------------------------------------
a = (
1, 2,
3
)
----------------------------------------
----------------------------------------
print a
----------------------------------------
(1, 2, 3)
```

`InteractiveConsole`类实现了一个交互控制台，类似你启动的Python解释器交互模式。控制台可以是活动的(自动调用函数到达下一行) 或是被动的(当有新数据时调用push方法)。默认使用内建的`raw_input`函数。

**Example 2-48. 使用 code 模块模拟交互解释器**
File: code-example-2.py
```python
import code

console = code.InteractiveConsole()
console.interact()
```
**输出结果**
```
Python 1.5.2
Copyright 1991-1995 Stichting Mathematisch Centrum, Amsterdam
>>> a = (
... 1,
... 2,
... 3
... )
>>> print a
(1, 2, 3)
```

Example 2-49中的脚本定义了一个`keyboard`函数，它允许你在程序中手动控制交互解释器。

**Example 2-49. 使用 code 模块实现简单的 Debugging**
File: code-example-3.py
```python
def keyboard(banner=None):
    import code, sys

    # use exception trick to pick up the current frame
    try:
        raise None
    except:
        frame = sys.exc_info()[2].tb_frame.f_back

    # evaluate commands in current namespace
    namespace = frame.f_globals.copy()
    namespace.update(frame.f_locals)

    code.interact(banner=banner, local=namespace)

def func():
    print "START"
    a = 10
    keyboard()
    print "END"

func()
```
**输出结果**
```
START
Python 1.5.2
Copyright 1991-1995 Stichting Mathematisch Centrum, Amsterdam
>>> print a
10
>>> print keyboard
<function keyboard at 9032c8>
^Z
END
```

---

## 3. 线程和进程
> 引言："Well, since you last asked us to stop, this thread has moved from discussing languages suitable for professional programmers via accidental users to computer-phobic users. A few more iterations can make this thread really interesting..."
> — eff-bot, June 1996

### 3.1 概览
本章将介绍标准Python解释器中所提供的线程支持模块（注意线程支持模块是可选的，有可能在一些Python解释器中不可用），还涵盖了一些Unix和Windows下用于执行外部进程的模块。

#### 3.1.1 线程
执行Python程序的时候，是按照从主模块顶端向下执行的。循环用于重复执行部分代码，函数和方法会将控制临时移交到程序的另一部分。通过线程，你的程序可以在同时处理多个任务，每个线程都有它自己的控制流，所以你可以在一个线程里从文件读取数据，另个向屏幕输出内容。

为了保证两个线程可以同时访问相同的内部数据，Python使用了global interpreter lock (全局解释器锁)。在同一时间只可能有一个线程执行Python代码；Python实际上是自动地在一段很短的时间后切换到下个线程执行，或者等待一个线程执行一项需要时间的操作(例如等待通过socket传输的数据，或是从文件中读取数据)。

全局锁事实上并不能避免你程序中的问题，多个线程尝试访问相同的数据会导致异常状态。例如以下的代码：
```python
def getitem(key):
    item = cache.get(key)
    if item is None:
        # not in cache; create a new one
        item = create_new_item(key)
        cache[key] = item
    return item
```
如果不同的线程先后使用相同的key调用这里的`getitem`方法，那么它们很可能会导致相同的参数调用两次`create_new_item`。大多时候这样做没有问题，但在某些时候会导致严重错误。不过你可以使用lock objects来同步线程，一个线程只能拥有一个lock object，这样就可以确保某个时刻只有一个线程执行`getitem`函数。

#### 3.1.2 进程
在大多现代操作系统中，每个程序在它自身的进程( process )内执行。我们通过在shell中键入命令或直接在菜单中选择来执行一个程序/进程。Python允许你在一个脚本内执行一个新的程序。大多进程相关函数通过os模块定义，相关内容请参阅第1.4.4小节。

---

### 3.2 threading 模块
(可选) threading模块为线程提供了一个高级接口，它源自Java的线程实现。和低级的thread模块相同，只有你在编译解释器时打开了线程支持才可以使用它。

你只需要继承`Thread`类，定义好`run`方法，就可以创建一个新的线程。使用时首先创建该类的一个或多个实例，然后调用`start`方法，这样每个实例的`run`方法都会运行在它自己的线程里。

**Example 3-1. 使用 threading 模块**
File: threading-example-1.py
```python
import threading
import time, random

class Counter:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = 0

    def increment(self):
        self.lock.acquire() # critical section
        self.value = value = self.value + 1
        self.lock.release()
        return value

counter = Counter()

class Worker(threading.Thread):
    def run(self):
        for i in range(10):
            # pretend we're doing something that takes 10?00 ms
            value = counter.increment() # increment global counter
            time.sleep(random.randint(10, 100) / 1000.0)
            print self.getName(), "-- task", i, "finished", value

#
# try it
for i in range(10):
    Worker().start() # start a worker
```
**输出结果**
```
Thread-1 -- task 0 finished 1
Thread-3 -- task 0 finished 3
Thread-7 -- task 0 finished 8
Thread-1 -- task 1 finished 7
Thread-4 -- task 0 finished 4
Thread-5 -- task 0 finished 5
Thread-8 -- task 0 finished 9
Thread-6 -- task 0 finished 6
...
Thread-6 -- task 9 finished 98
Thread-4 -- task 9 finished 99
Thread-9 -- task 9 finished 100
```

Example 3-1使用了Lock对象来在全局Counter对象里创建临界区 (critical section)。如果删除了acquire和release语句，那么Counter很可能不会到达100。

---

### 3.3 Queue 模块
Queue模块提供了一个线程安全的队列 (queue) 实现，你可以通过它在多个线程里安全访问同个对象。

**Example 3-2. 使用 Queue 模块**
File: queue-example-1.py
```python
import threading
import Queue
import time, random

WORKERS = 2

class Worker(threading.Thread):
    def __init__(self, queue):
        self.__queue = queue
        threading.Thread.__init__(self)

    def run(self):
        while 1:
            item = self.__queue.get()
            if item is None:
                break # reached end of queue
            # pretend we're doing something that takes 10?00 ms
            time.sleep(random.randint(10, 100) / 1000.0)
            print "task", item, "finished"

#
# try it
queue = Queue.Queue(0)

for i in range(WORKERS):
    Worker(queue).start() # start a worker

for i in range(10):
    queue.put(i)

for i in range(WORKERS):
    queue.put(None) # add end-of-queue markers
```
**输出结果**
```
task 1 finished
task 0 finished
task 3 finished
task 2 finished
task 4 finished
task 5 finished
task 7 finished
task 6 finished
task 9 finished
task 8 finished
```

Example 3-3展示了如何限制队列的大小。如果队列满了，那么控制主线程 (producer threads) 被阻塞，等待项目被弹出 (pop off)。

**Example 3-3. 使用限制大小的 Queue 模块**
File: queue-example-2.py
```python
import threading
import Queue
import time, random

WORKERS = 2

class Worker(threading.Thread):
    def __init__(self, queue):
        self.__queue = queue
        threading.Thread.__init__(self)

    def run(self):
        while 1:
            item = self.__queue.get()
            if item is None:
                break # reached end of queue
            # pretend we're doing something that takes 10?00 ms
            time.sleep(random.randint(10, 100) / 1000.0)
            print "task", item, "finished"

#
# run with limited queue
queue = Queue.Queue(3)

for i in range(WORKERS):
    Worker(queue).start() # start a worker

for item in range(10):
    print "push", item
    queue.put(item)

for i in range(WORKERS):
    queue.put(None) # add end-of-queue markers
```
**输出结果**
```
push 0
push 1
push 2
push 3
push 4
push 5
task 0 finished
push 6
task 1 finished
push 7
task 2 finished
push 8
push 9
task 3 finished
task 4 finished
task 6 finished
task 5 finished
task 7 finished
task 9 finished
task 8 finished
```

你可以通过继承Queue类来修改它的行为。Example 3-4为我们展示了一个简单的具有优先级的队列，它接受一个元组作为参数，元组的第一个成员表示优先级(数值越小优先级越高)。

**Example 3-4. 使用 Queue 模块实现优先级队列**
File: queue-example-3.py
```python
import Queue
import bisect

Empty = Queue.Empty

class PriorityQueue(Queue.Queue):
    "Thread-safe priority queue"
    def _put(self, item):
        # insert in order
        bisect.insort(self.queue, item)

#
# try it
queue = PriorityQueue(0)

# add items out of order
queue.put((20, "second"))
queue.put((10, "first"))
queue.put((30, "third"))

# print queue contents
try:
    while 1:
        print queue.get_nowait()
except Empty:
    pass
```
**输出结果**
```
third
second
first
```

Example 3-5展示了一个简单的堆栈 (stack) 实现 (末尾添加，头部弹出，而非头部添加，头部弹出)。

**Example 3-5. 使用 Queue 模块实现一个堆栈**
File: queue-example-4.py
```python
import Queue

Empty = Queue.Empty

class Stack(Queue.Queue):
    "Thread-safe stack"
    def _put(self, item):
        # insert at the beginning of queue, not at the end
        self.queue.insert(0, item)

    # method aliases
    push = Queue.Queue.put
    pop = Queue.Queue.get
    pop_nowait = Queue.Queue.get_nowait

#
# try it
stack = Stack(0)

# push items on stack
stack.push("first")
stack.push("second")
stack.push("third")

# print stack contents
try:
    while 1:
        print stack.pop_nowait()
except Empty:
    pass
```
**输出结果**
```
third
second
first
```

---

### 3.4 thread 模块
(可选) thread模块提为线程提供了一个低级 (low_level) 的接口，只有你在编译解释器时打开了线程支持才可以使用它。如果没有特殊需要，最好使用高级接口threading模块替代。

**Example 3-6. 使用 thread 模块**
File: thread-example-1.py
```python
import thread
import time, random

def worker():
    for i in range(50):
        # pretend we're doing something that takes 10?00 ms
        print thread.get_ident(), "-- task", i, "finished"
        time.sleep(random.randint(10, 100) / 1000.0)

#
# try it out!
for i in range(2):
    thread.start_new_thread(worker, ())

time.sleep(1)

print "goodbye!"
```
**输出结果**
```
311 -- task 0 finished
265 -- task 0 finished
265 -- task 1 finished
311 -- task 1 finished
...
265 -- task 17 finished
311 -- task 13 finished
265 -- task 18 finished
goodbye!
```

> 注意：当主程序退出的时候，所有的线程也随着退出。而threading模块不存在这个问题（该行为可改变）。

---

### 3.5 commands 模块
(只用于Unix) commands模块包含一些用于执行外部命令的函数。

**Example 3-7. 使用 commands 模块**
File: commands-example-1.py
```python
import commands

stat, output = commands.getstatusoutput("ls -lR")

print "status", "=>", stat
print "output", "=>", len(output), "bytes"
```
**输出结果**
```
status => 0
output => 171046 bytes
```

---

### 3.6 pipes 模块
(只用于Unix) pipes模块提供了 "转换管道 (conversion pipelines)" 的支持。你可以创建包含许多外部工具调用的管道来处理多个文件。

**Example 3-8. 使用 pipes 模块**
File: pipes-example-1.py
```python
import pipes

t = pipes.Template()

# create a pipeline
# 这里 " - " 代表从标准输入读入内容
t.append("sort", "--")
t.append("uniq", "--")

# filter some text
# 这里空字符串代表标准输出
t.copy("samples/sample.txt", "")
```
**输出结果**
```
Alan Jones (sensible party)
Kevin Phillips-Bong (slightly silly)
Tarquin Fin-tim-lin-bin-whin-bim-lin-bus-stop-F'tang-F'tang-Olé-Biscuitbarrel
```

---

### 3.7 popen2 模块
popen2模块允许你执行外部命令，并通过流来分别访问它的stdin和stdout ( 可能还有stderr )。在python 1.5.2以及之前版本，该模块只存在于Unix平台上，2.0后Windows下也实现了该函数。

Example 3-9展示了如何使用该模块来给字符串排序。

**Example 3-9. 使用 popen2 模块对字符串排序Module to Sort Strings**
File: popen2-example-1.py
```python
import popen2, string

fin, fout = popen2.popen2("sort")

fout.write("foo\n")
fout.write("bar\n")
fout.close()

print fin.readline(),
print fin.readline(),
fin.close()
```
**输出结果**
```
bar
foo
```

Example 3-10展示了如何使用该模块控制应用程序。

**Example 3-10. 使用 popen2 模块控制 gnuchess**
File: popen2-example-2.py
```python
import popen2
import string

class Chess:
    "Interface class for chesstool-compatible programs"
    def __init__(self, engine = "gnuchessc"):
        self.fin, self.fout = popen2.popen2(engine)
        s = self.fin.readline()
        if s != "Chess\n":
            raise IOError, "incompatible chess program"

    def move(self, move):
        self.fout.write(move + "\n")
        self.fout.flush()
        my = self.fin.readline()
        if my == "Illegal move":
            raise ValueError, "illegal move"
        his = self.fin.readline()
        return string.split(his)[2]

    def quit(self):
        self.fout.write("quit\n")
        self.fout.flush()

#
# play a few moves
g = Chess()
print g.move("a2a4")
print g.move("b2b3")
g.quit()
```
**输出结果**
```
b8c6
e7e5
```

---

### 3.8 signal 模块
你可以使用signal模块配置你自己的信号处理器 (signal handler)，当解释器收到某个信号时，信号处理器会立即执行。

**Example 3-11. 使用 signal 模块**
File: signal-example-1.py
```python
import signal
import time

def handler(signo, frame):
    print "got signal", signo

signal.signal(signal.SIGALRM, handler)

# wake me up in two seconds
signal.alarm(2)

now = time.time()

time.sleep(200)

print "slept for", time.time() - now, "seconds"
```
**输出结果**
```
got signal 14
slept for 1.99262607098 seconds
```

---

## 4. 数据表示
> 引言："PALO ALTO, Calif. - Intel says its Pentium Pro and new Pentium II chips have a flaw that can cause computers to sometimes make mistakes but said the problems could be fixed easily with rewritten software."
> — Reuters telegram

### 4.1 概览
本章描述了一些用于在Python对象和其他数据表示类型间相互转换的模块，这些模块通常用于读写特定的文件格式或是储存/取出Python变量。

#### 4.1.1 二进制数据
Python提供了一些用于二进制数据解码/编码的模块：
- `struct`模块：用于在二进制数据结构(例如C中的struct)和Python元组间转换。
- `array`模块：将二进制数据阵列 (C arrays)封装为Python序列对象。

#### 4.1.2 自描述格式
`marshal`和`pickle`模块用于在不同的Python程序间共享/传递数据：
- `marshal`模块：使用了简单的自描述格式，支持大多的内建数据类型，包括code对象。Python自身也使用了这个格式来储存编译后代码( .pyc 文件)。
- `pickle`模块：提供了更复杂的格式，支持用户定义的类、自引用数据结构等。pickle是用Python写的，相对来说速度较慢，不过还有一个cPickle模块，使用C实现了相同的功能，速度和marshal不相上下。

#### 4.1.3 输出格式
一些模块提供了增强的格式化输出，用来补充内建的repr函数和%字符串格式化操作符：
- `pprint`模块：几乎可以将任何Python数据结构很好地打印出来(提高可读性)。
- `repr`模块：可以用来替换内建同名函数。该模块与内建函数不同的是它限制了很多输出形式：只会输出字符串的前30个字符，只打印嵌套数据结构的几个等级等。

#### 4.1.4 编码二进制数据
Python支持大部分常见二进制编码，例如base64、binhex (一种Macintosh格式)、quoted printable、以及uu编码。

---

### 4.2 array 模块
array模块实现了一个有效的阵列储存类型。阵列和列表类似，但其中所有的项目必须为相同的类型，该类型在阵列创建时指定。

Example 4-1创建了一个array对象，然后使用`tostring`方法将内部缓冲区复制到字符串。

**Example 4-1. 使用 array 模块将数列转换为字符串**
File: array-example-1.py
```python
import array

a = array.array("B", range(16)) # unsigned char
b = array.array("h", range(16)) # signed short

print a
print repr(a.tostring())
print b
print repr(b.tostring())
```
**输出结果**
```
array('B', [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
'\000\001\002\003\004\005\006\007\010\011\012\013\014\015\016\017'
array('h', [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
'\000\000\001\000\002\000\003\000\004\000\005\000\006\000\007\000\010\000\011\000\012\000\013\000\014\000\015\000\016\000\017\000'
```

array对象可以作为一个普通列表对待，不过你不能连接两个不同类型的阵列。

**Example 4-2. 作为普通序列操作阵列**
File: array-example-2.py
```python
import array

a = array.array("B", [1, 2, 3])
a.append(4)
a = a + a
a = a[2:-2]

print a
print repr(a.tostring())
for i in a:
    print i,
```
**输出结果**
```
array('B', [3, 4, 1, 2])
'\003\004\001\002'
3 4 1 2
```

该模块还提供了用于转换原始二进制数据到整数序列(或浮点数数列, 具体情况决定)的方法。

**Example 4-3. 使用阵列将字符串转换为整数列表**
File: array-example-3.py
```python
import array

a = array.array("i", "fish license") # signed integer

print a
print repr(a.tostring())
print a.tolist()
```
**输出结果**
```
array('i', [1752394086, 1667853344, 1702063717])
'fish license'
[1752394086, 1667853344, 1702063717]
```

Example 4-4展示了如何使用该模块判断当前平台的字节序 ( endianess )。

**Example 4-4. 使用 array 模块判断平台字节序**
File: array-example-4.py
```python
import array

def little_endian():
    return ord(array.array("i",[1]).tostring()[0])

if little_endian():
    print "little-endian platform (intel, alpha)"
else:
    print "big-endian platform (motorola, sparc)"
```
**输出结果**
```
big-endian platform (motorola, sparc)
```

Python 2.0及以后版本提供了`sys.byteorder`属性，可以更简单地判断字节序 (属性值为 "little " 或 "big " )。

**Example 4-5. 使用 sys.byteorder 属性判断平台字节序( Python 2.0 及以后)**
File: sys-byteorder-example-1.py
```python
import sys

# 2.0 and later
if sys.byteorder == "little":
    print "little-endian platform (intel, alpha)"
else:
    print "big-endian platform (motorola, sparc)"
```
**输出结果**
```
big-endian platform (motorola, sparc)
```

---

### 4.3 struct 模块
struct模块用于转换二进制字符串和Python元组。`pack`函数接受格式字符串以及额外参数，根据指定格式将额外参数转换为二进制字符串。`upack`函数接受一个字符串作为参数，返回一个元组。

**Example 4-6. 使用 struct 模块**
File: struct-example-1.py
```python
import struct

# native byteorder
buffer = struct.pack("ihb", 1, 2, 3)
print repr(buffer)
print struct.unpack("ihb", buffer)

# data from a sequence, network byteorder
data = [1, 2, 3]
buffer = apply(struct.pack, ("!ihb",) + tuple(data))

print repr(buffer)
print struct.unpack("!ihb", buffer)

# in 2.0, the apply statement can also be written as:
# buffer = struct.pack("!ihb", *data)
```
**输出结果**
```
'\001\000\000\000\002\000\003'
(1, 2, 3)
'\000\000\000\001\000\002\003'
(1, 2, 3)
```

---

### 4.4 xdrlib 模块
xdrlib模块用于在Python数据类型和Sun的external data representation (XDR)间相互转化。

**Example 4-7. 使用 xdrlib 模块**
File: xdrlib-example-1.py
```python
import xdrlib

#
# create a packer and add some data to it
p = xdrlib.Packer()
p.pack_uint(1)
p.pack_string("spam")

data = p.get_buffer()
print "packed:", repr(data)

#
# create an unpacker and use it to decode the data
u = xdrlib.Unpacker(data)
print "unpacked:", u.unpack_uint(), repr(u.unpack_string())
u.done()
```
**输出结果**
```
packed: '\000\000\000\001\000\000\000\004spam'
unpacked: 1 'spam'
```

Sun在remote procedure call (RPC)协议中使用了XDR格式，Example 4-8虽然不完整，但它展示了如何建立一个RPC请求包。

**Example 4-8. 使用 xdrlib 模块发送 RPC 调用包**
File: xdrlib-example-2.py
```python
import xdrlib

# some constants (see the RPC specs for details)
RPC_CALL = 1
RPC_VERSION = 2

MY_PROGRAM_ID = 1234 # assigned by Sun
MY_VERSION_ID = 1000
MY_TIME_PROCEDURE_ID = 9999

AUTH_NULL = 0

transaction = 1

p = xdrlib.Packer()

# send a Sun RPC call package
p.pack_uint(transaction)
p.pack_enum(RPC_CALL)
p.pack_uint(RPC_VERSION)
p.pack_uint(MY_PROGRAM_ID)
p.pack_uint(MY_VERSION_ID)
p.pack_uint(MY_TIME_PROCEDURE_ID)
p.pack_enum(AUTH_NULL)
p.pack_uint(0)
p.pack_enum(AUTH_NULL)
p.pack_uint(0)

print repr(p.get_buffer())
```
**输出结果**
```
'\000\000\000\001\000\000\000\001\000\000\000\002\000\000\004\322 \000\000\003\350\000\000\'\017\000\000\000\000\000\000\000\000\000 \000\000\000\000\000\000\000'
```

---

### 4.5 marshal 模块
marshal模块可以把不连续的数据组合起来，与字符串相互转化，这样它们就可以写入文件或是在网络中传输。

marshal模块使用了简单的自描述格式，对于每个数据项目，格式化后的字符串都包含一个类型代码，然后是一个或多个类型标识区域。整数使用小字节序 ( little-endian order )储存，字符串储存时和它自身内容长度相同(可能包含空字节)，元组由组成它的对象组合表示。

**Example 4-9. 使用 marshal 模块组合不连续数据**
File: marshal-example-1.py
```python
import marshal

value = (
    "this is a string",
    [1, 2, 3, 4],
    ("more tuples", 1.0, 2.3, 4.5),
    "this is yet another string"
)

data = marshal.dumps(value)

# intermediate format
print type(data), len(data)
print "-"*50
print repr(data)
print "-"*50
print marshal.loads(data)
```
**输出结果**
```
<type 'string'> 118
--------------------------------------------------
'(\004\000\000\000s\020\000\000\000this is a string
[\004\000\000\000i\001\000\000\000i\002\000\000\000
i\003\000\000\000i\004\000\000\000(\004\000\000\000
s\013\000\000\000more tuplesf\0031.0f\0032.3f\0034.
5s\032\000\000\000this is yet another string'
--------------------------------------------------
('this is a string', [1, 2, 3, 4], ('more tuples',
1.0, 2.3, 4.5), 'this is yet another string')
```

marshal模块还可以处理code对象，它用于储存预编译的Python模块。

**Example 4-10. 使用 marshal 模块处理代码**
File: marshal-example-2.py
```python
import marshal

script = """
print 'hello'
"""

code = compile(script, "<script>", "exec")
data = marshal.dumps(code)

# intermediate format
print type(data), len(data)
print "-"*50
print repr(data)
print "-"*50

exec marshal.loads(data)
```
**输出结果**
```
<type 'string'> 81
--------------------------------------------------
'c\000\000\000\000\001\000\000\000s\017\000\000\00
0\177\000\000\177\002\000d\000\000GHd\001\000S(\00
2\000\000\000s\005\000\000\000helloN(\000\000\000\
000(\000\000\000\000s\010\000\000\000<script>s\001
\000\000\000?\002\000s\000\000\000\000'
--------------------------------------------------
hello
```

---

### 4.6 pickle 模块
pickle模块同marshal模块相同，将数据连续化，便于保存传输。它比marshal要慢一些，但它可以处理类实例、共享的元素、以及递归数据结构等。

**Example 4-11. 使用 pickle 模块**
File: pickle-example-1.py
```python
import pickle

value = (
    "this is a string",
    [1, 2, 3, 4],
    ("more tuples", 1.0, 2.3, 4.5),
    "this is yet another string"
)

data = pickle.dumps(value)

# intermediate format
print type(data), len(data)
print "-"*50
print data
print "-"*50
print pickle.loads(data)
```
**输出结果**
```
<type 'string'> 121
--------------------------------------------------
(I1
p0
(S'this is a string'
p1
(lp2
aI2
aI3
aI4
a(S'more tuples'
p3
F1.0
F2.3
F4.5
tp4
S'this is yet another string'
p5
tp6
.
--------------------------------------------------
('this is a string', [1, 2, 3, 4], ('more tuples',
1.0, 2.3, 4.5), 'this is yet another string')
```

另一方面，pickle不能处理code对象，你可以参阅copy_reg模块来完成这个。默认情况下，pickle使用基于文本的格式，你也可以使用二进制格式，这样数字和二进制字符串就会以紧密的格式储存，文件会更小。

**Example 4-12. 使用 pickle 模块的二进制模式**
File: pickle-example-2.py
```python
import pickle
import math

value = (
    "this is a long string" * 100,
    [1.2345678, 2.3456789, 3.4567890] * 100
)

# text mode
data = pickle.dumps(value)
print type(data), len(data), pickle.loads(data) == value

# binary mode
data = pickle.dumps(value, 1)
print type(data), len(data), pickle.loads(data) == value
```

---

### 4.7 cPickle 模块
(可选, 注意大小写) cPickle模块是针对pickle模块的一个更快的C语言实现。

**Example 4-13. 使用 cPickle 模块**
File: cpickle-example-1.py
```python
try:
    import cPickle
    pickle = cPickle
except ImportError:
    import pickle
```

---

### 4.8 copy_reg 模块
你可以使用copy_reg模块注册你自己的扩展类型，这样pickle和copy模块就会知道如何处理非标准类型。

例如，标准的pickle实现不能用来处理Python code对象，如下所示：
```python
File: copy-reg-example-1.py
import pickle

CODE = """
print 'good evening'
"""

code = compile(CODE, "<string>", "exec")
exec code
exec pickle.loads(pickle.dumps(code))
```
执行后会输出：
```
good evening
Traceback (innermost last):
pickle.PicklingError: can't pickle 'code' objects
```

我们可以注册一个code对象处理器来完成目标，处理器应包含两个部分：一个pickler，接受code对象并返回一个只包含简单数据类型的元组；以及一个unpickler，作用相反，接受这样的元组作为参数。

**Example 4-14. 使用 copy_reg 模块实现 code 对象的 pickle 操作**
File: copy-reg-example-2.py
```python
import copy_reg
import pickle, marshal, types

#
# register a pickle handler for code objects

def code_unpickler(data):
    return marshal.loads(data)

def code_pickler(code):
    return code_unpickler, (marshal.dumps(code),)

copy_reg.pickle(types.CodeType, code_pickler, code_unpickler)

#
# try it out

CODE = """
print "suppose he's got a pointed stick"
"""

code = compile(CODE, "<string>", "exec")
exec code
exec pickle.loads(pickle.dumps(code))
```
**输出结果**
```
suppose he's got a pointed stick
suppose he's got a pointed stick
```

> 注意：如果你是在网络中传输pickle后的数据，那么请确保自定义的unpickler在数据接收端也是可用的。

Example 4-15展示了如何实现pickle一个打开的文件对象。

**Example 4-15. 使用 copy_reg 模块实现文件对象的 pickle 操作**
File: copy-reg-example-3.py
```python
import copy_reg
import pickle, types
import StringIO

#
# register a pickle handler for file objects

def file_unpickler(position, data):
    file = StringIO.StringIO(data)
    file.seek(position)
    return file

def file_pickler(code):
    position = file.tell()
    file.seek(0)
    data = file.read()
    file.seek(position)
    return file_unpickler, (position, data)

copy_reg.pickle(types.FileType, file_pickler, file_unpickler)

#
# try it out

file = open("samples/sample.txt", "rb")
print file.read(120),
print "<here>",
print pickle.loads(pickle.dumps(file)).read()
```
**输出结果**
```
We will perhaps eventually be writing only small
modules, which are identified by name as they are
used to build larger <here> ones, so that devices like
indentation, rather than delimiters, might become
feasible for expressing local structure in the
source language. -- Donald E. Knuth, December 1974
```

---

### 4.9 pprint 模块
pprint模块( pretty printer )用于打印Python数据结构，当你在命令行下打印特定数据结构时你会发现它很有用(输出格式比较整齐，便于阅读)。

**Example 4-16. 使用 pprint 模块**
File: pprint-example-1.py
```python
import pprint

data = (
    "this is a string", [1, 2, 3, 4], ("more tuples",
    1.0, 2.3, 4.5), "this is yet another string"
)

pprint.pprint(data)
```
**输出结果**
```
('this is a string',
 [1, 2, 3, 4],
 ('more tuples', 1.0, 2.3, 4.5),
 'this is yet another string')
```

---

### 4.10 repr 模块
repr模块提供了内建repr函数的另个版本，它限制了很多(字符串长度、递归等)。

**Example 4-17. 使用 repr 模块**
File: repr-example-1.py
```python
# note: this overrides the built-in 'repr' function
from repr import repr

# an annoyingly recursive data structure
data = (
    "X" * 100000,
)
data = [data]
data.append(data)

print repr(data)
```
**输出结果**
```
[('XXXXXXXXXXXX...XXXXXXXXXXXXX',), [('XXXXXXXXXXXX...XXXXXXXXXX
XXX',), [('XXXXXXXXXXXX...XXXXXXXXXXXXX',), [('XXXXXXXXXXXX...XX
XXXXXXXXXXX',), [('XXXXXXXXXXXX...XXXXXXXXXXXXX',), [(...), [...
]]]]]]
```

---

### 4.11 base64 模块
base64编码体系用于将任意二进制数据转换为纯文本。它将一个3字节的二进制字节组转换为4个文本字符组储存，而且规定只允许以下集合中的字符出现：
```
ABCDEFGHIJKLMNOPQRSTUVWXYZ
abcdefghijklmnopqrstuvwxyz
0123456789+/
```
另外，`=`用于填充数据流的末尾。

Example 4-18展示了如何使用`encode`和`decode`函数操作文件对象。

**Example 4-18. 使用 base64 模块编码文件**
File: base64-example-1.py
```python
import base64

MESSAGE = "life of brian"

file = open("out.txt", "w")
file.write(MESSAGE)
file.close()

base64.encode(open("out.txt"), open("out.b64", "w"))
base64.decode(open("out.b64"), open("out.txt", "w"))

print "original:", repr(MESSAGE)
print "encoded message:", repr(open("out.b64").read())
print "decoded message:", repr(open("out.txt").read())
```
**输出结果**
```
original: 'life of brian'
encoded message: 'bGlmZSBvZiBicmlhbg==\012'
decoded message: 'life of brian'
```

Example 4-19展示了如何使用`encodestring`和`decodestring`函数在字符串间转换。它们是encode和decode函数的顶层封装，使用StringIO对象处理输入和输出。

**Example 4-19. 使用 base64 模块编码字符串**
File: base64-example-2.py
```python
import base64

MESSAGE = "life of brian"

data = base64.encodestring(MESSAGE)
original_data = base64.decodestring(data)

print "original:", repr(MESSAGE)
print "encoded data:", repr(data)
print "decoded data:", repr(original_data)
```
**输出结果**
```
original: 'life of brian'
encoded data: 'bGlmZSBvZiBicmlhbg==\012'
decoded data: 'life of brian'
```

Example 4-20展示了如何将用户名和密码转换为HTTP基本身份验证字符串。

**Example 4-20. 使用 base64 模块做基本验证**
File: base64-example-3.py
```python
import base64

def getbasic(user, password):
    # basic authentication (according to HTTP)
    return base64.encodestring(user + ":" + password)

print getbasic("Aladdin", "open sesame")
```
**输出结果**
```
'QWxhZGRpbjpvcGVuIHNlc2FtZQ=='
```

最后，Example 4-21展示了一个实用小工具，它可以把GIF格式转换为Python脚本，便于使用Tkinter库。

**Example 4-21. 使用 base64 为 Tkinter 封装 GIF 格式**
File: base64-example-4.py
```python
import base64, sys

if not sys.argv[1:]:
    print "Usage: gif2tk.py giffile >pyfile"
    sys.exit(1)

data = open(sys.argv[1], "rb").read()
if data[:4] != "GIF8":
    print sys.argv[1], "is not a GIF file"
    sys.exit(1)

print '# generated from', sys.argv[1], 'by gif2tk.py'
print
print 'from Tkinter import PhotoImage'
print
print 'image = PhotoImage(data="""'
print base64.encodestring(data),
print '""")'
```
**输出结果**
```
# generated from samples/sample.gif by gif2tk.py

from Tkinter import PhotoImage

image = PhotoImage(data="""
R0lGODlhoAB4APcAAAAAAIAAAACAAICAAAAAgIAAgACAgICAgAQEBIwEBIyMBJRUlISE
/LRUBAQE
AjmQBFmQBnmQCJmQCrmQDNmQDvmQEBmREnkRAQEAOw==
""")
```

---

### 4.12 binhex 模块
binhex模块用于到Macintosh BinHex格式的相互转化。

**Example 4-22. 使用 binhex 模块**
File: binhex-example-1.py
```python
import binhex
import sys

infile = "samples/sample.jpg"
binhex.binhex(infile, sys.stdout)
```
**输出结果**
```
(This file must be converted with BinHex 4.0)
:#R0KEA"XC5jUF'F!2j!)!*!%%TS!N!4RdrrBrq!!%%T'58B!!3%!!!%!!3!!rpX
h+5``-63d0"mR16di-M`Z-c3brpX!3`%*#3N-#``B$3dB-L%F)6+3-[r!!"%)!)!
!3`!)"JB("J8)"`F(#3N)#J`8$3`,#``C%K-2&"dD(aiG'K`F)#3Z*b!L,#-F(#J
!J!-")J!#%3%$%3(ra!!I!!!""3'3"J#3#!%#!`3&"JF)#3S,rm3!Y4!!!J%$!`)
%!`8&"!3!!!&p!3)$!!34"4)K-8%'%e&K"b*a&$+"ND%))d+a`495dI!N-f*bJJN
...
```

该模块有两个函数：`binhex`和`hexbin`。

---

### 4.13 quopri 模块
quopri模块基于MIME标准实现了引用的可打印编码( quoted printable encoding )。这样的编码可以将不包含或只包含一部分U.S. ASCII文本的信息，例如大多欧洲语言、中文，转换为只包含U.S. ASCII的信息，在一些老式的mail代理中你会发现这很有用，因为它们一般不支持特殊字符。

**Example 4-23. 使用 quopri 模块**
File: quopri-example-1.py
```python
import quopri
import StringIO

# helpers (the quopri module only supports file-to-file conversion)
def encodestring(instring, tabs=0):
    outfile = StringIO.StringIO()
    quopri.encode(StringIO.StringIO(instring), outfile, tabs)
    return outfile.getvalue()

def decodestring(instring):
    outfile = StringIO.StringIO()
    quopri.decode(StringIO.StringIO(instring), outfile)
    return outfile.getvalue()

#
# try it out
MESSAGE = "å i åa ä e ö!"

encoded_message = encodestring(MESSAGE)
decoded_message = decodestring(encoded_message)

print "original:", MESSAGE
print "encoded message:", repr(encoded_message)
print "decoded message:", decoded_message
```
**输出结果**
```
original: å i åa ä e ö!
encoded message: '=E5 i =E5a =E4 e =F6!\012'
decoded message: å i åa ä e ö!
```

如Example 4-23所示，非U.S.字符通过等号 (= ) 附加两个十六进制字符来表示。这里需要注意等号也是使用这样的方式( "=3D " )来表示的，以及换行符("=20 " )。其他字符不会被改变，所以如果你没有用太多的怪异字符的话，编码后字符串依然可读性很好。

---

### 4.14 uu 模块
uu编码体系用于将任意二进制数据转换为普通文本格式。该格式在新闻组中很流行，但逐渐被base64编码取代。

uu编码将每个3字节(24位)的数据组转换为4个可打印字符(每个字符6位)，使用从chr(32) (空格) 到chr(95) 的字符。uu编码通常会使数据大小增加40%。

一个编码后的数据流以一个新行开始，它包含文件的权限( Unix 格式)和文件名，以end行结尾：
```
begin 666 sample.jpg
M_]C_X 02D9)1@ ! 0 0 ! #_VP!# @&!@<&!0@'!P<)'0@*#!0-# L+
...more lines like this...
end
```

uu模块提供了两个函数：`encode`和`decode`。`encode(infile, outfile, filename)`函数从编码输入文件中的数据，然后写入到输出文件中。infile和outfile可以是文件名或文件对象，filename参数作为起始域的文件名写入。

**Example 4-24. 使用 uu 模块编码二进制文件**
File: uu-example-1.py
```python
import uu
import os, sys

infile = "samples/sample.jpg"
uu.encode(open(infile, "rb"), sys.stdout, os.path.basename(infile))
```

`decode(infile, outfile)`函数用来解码uu编码的数据，同样地，参数可以是文件名也可以是文件对象。

**Example 4-25. 使用 uu 模块解码 uu 格式的文件**
File: uu-example-2.py
```python
import uu
import StringIO

infile = "samples/sample.uue"
outfile = "samples/sample.jpg"

#
# decode
fo = StringIO.StringIO()
fi = open(infile)
uu.decode(fi, fo)

#
# compare with original data file
data = open(outfile, "rb").read()
if fo.getvalue() == data:
    print len(data), "bytes ok"
```

---

### 4.15 binascii 模块
binascii提供了多个编码的支持函数，包括base64、binhex、以及uu。2.0及以后版本中，你还可以使用它在二进制数据和十六进制字符串中相互转换。

**Example 4-26. 使用 binascii 模块**
File: binascii-example-1.py
```python
import binascii

text = "hello, mrs teal"

data = binascii.b2a_base64(text)
text = binascii.a2b_base64(data)
print text, "<=>", repr(data)

data = binascii.b2a_uu(text)
text = binascii.a2b_uu(data)
print text, "<=>", repr(data)

data = binascii.b2a_hqx(text)
text = binascii.a2b_hqx(data)[0]
print text, "<=>", repr(data)

# 2.0 and newer
data = binascii.b2a_hex(text)
text = binascii.a2b_hex(data)
print text, "<=>", repr(data)
```
**输出结果**
```
hello, mrs teal <=> 'aGVsbG8sIG1ycyB0ZWFs\012'
hello, mrs teal <=> '/:&5L;&\\L(&UR<R!T96%L\012'
hello, mrs teal <=> 'D\'9XE\'mX)\'ebFb"dC@&X'
hello, mrs teal <=> '68656c6c6f2c206d7273207465616c'
```

---

## 5. 文件格式
### 5.1 概览
本章描述了用于处理不同文件格式的模块，涵盖标记语言、配置文件、压缩档案格式等相关处理能力。

#### 5.1.1 Markup 语言
Python提供了一些用于处理可扩展标记语言( Extensible Markup Language , XML )、超文本标记语言( Hypertext Markup Language , HTML )的扩展，同样提供了对标准通用标记语言( Standard Generalized Markup Language , SGML )的支持。

所有这些格式都有着相同的结构，因为HTML和XML都来自SGML。每个文档都是由起始标签( start tags )、结束标签( end tags )、文本(又叫字符数据)、以及实体引用( entity references )构成：
```xml
<document name="sample.xml">
    <header>This is a header</header>
    <body>This is the body text. The text can contain
    plain text (&quot;character data&quot;), tags, and entities. </body>
</document>
```

在这个例子中，`<document>`、`<header>`、以及`<body>`是起始标签。每个起始标签都有一个对应的结束标签，使用斜线 "/" 标记。起始标签可以包含多个属性，比如这里的name属性。起始标签和它对应的结束标签中的任何东西被称为元素( element )，这里document元素包含header和body两个元素。

`&quot;`是一个字符实体( character entity )，用于在文本区域中表示特殊的保留字符，使用&指示。这里它代表一个引号，常见字符实体还有 "< ( &lt; ) " 和 " > ( &gt; ) "。

XML、HTML、SGML的核心差异：
- XML中，所有元素必须有起始和结束标签，所有标签必须正确嵌套( well-formed )，XML是区分大小写的。
- HTML有很高灵活性，HTML语法分析器一般会自动补全缺失标签，也是区分大小写的，HTML使用规范定义的固定元素。
- SGML有着更高的灵活性，你可以使用自己的声明( declaration ) 定义源文件如何转换到元素结构，DTD ( document type description , 文件类型定义)可以用来检查结构并补全缺失标签。技术上来说，HTML和XML都是SGML应用。

Python提供的标记语言分析器：
- `sgmllib`：简单的SGML分析器，不会处理DTD，但可继承扩展。
- `htmllib`：基于SGML分析器的HTML支持，将格式输出工作交给formatter对象。
- XML支持：先前是`xmllib`，后来加入了`expat`模块，最新版本启用xml包作为工具集。

#### 5.1.2 配置文件
- `ConfigParser`模块：用于读取简单的配置文件，类似Windows下的INI文件。
- `netrc`模块：用于读取.netrc配置文件。
- `shlex`模块：用于读取类似shell脚本语法的配置文件。

#### 5.1.3 压缩档案格式
Python的标准库提供了对GZIP和ZIP ( 2.0及以后) 格式的支持，基于zlib模块，`gzip`和`zipfile`模块分别用来处理这类文件。

---

### 5.2 xmllib 模块
xmllib已在当前版本中申明不支持。xmllib模块提供了一个简单的XML语法分析器，使用正则表达式将XML数据分离。语法分析器只对文档做基本的检查，例如是否只有一个顶层元素，所有的标签是否匹配。

XML数据一块一块地发送给xmllib分析器(例如在网路中传输的数据)。分析器在遇到起始标签、数据区域、结束标签、和实体的时候调用不同的方法。如果你只是对某些标签感兴趣，你可以定义特殊的`start_tag`和`end_tag`方法，这里tag是标签名称。这些start函数使用它们对应标签的属性作为参数调用(传递时为一个字典)。

**Example 5-1. 使用 xmllib 模块获取元素的信息**
File: xmllib-example-1.py
```python
import xmllib

class Parser(xmllib.XMLParser):
    # get quotation number
    def __init__(self, file=None):
        xmllib.XMLParser.__init__(self)
        if file:
            self.load(file)

    def load(self, file):
        while 1:
            s = file.read(512)
            if not s:
                break
            self.feed(s)
        self.close()

    def start_quotation(self, attrs):
        print "id =>", attrs.get("id")
        raise EOFError

try:
    c = Parser()
    c.load(open("samples/sample.xml"))
except EOFError:
    pass
```
**输出结果**
```
id => 031
```

Example 5-2展示了一个简单(不完整)的内容输出引擎( rendering engine )。分析器有一个元素堆栈( `__tags` )，它连同文本片断传递给输出生成器。生成器会在style字典中查询当前标签的层次，如果不存在，它将根据样式表创建一个新的样式描述。

**Example 5-2. 使用 xmllib 模块**
File: xmllib-example-2.py
```python
import xmllib
import string, sys

STYLESHEET = {
    # each element can contribute one or more style elements
    "quotation": {"style": "italic"},
    "lang": {"weight": "bold"},
    "name": {"weight": "medium"},
}

class Parser(xmllib.XMLParser):
    # a simple styling engine
    def __init__(self, renderer):
        xmllib.XMLParser.__init__(self)
        self.__data = []
        self.__tags = []
        self.__renderer = renderer

    def load(self, file):
        while 1:
            s = file.read(8192)
            if not s:
                break
            self.feed(s)
        self.close()

    def handle_data(self, data):
        self.__data.append(data)

    def unknown_starttag(self, tag, attrs):
        if self.__data:
            text = string.join(self.__data, "")
            self.__renderer.text(self.__tags, text)
            self.__data = []
        self.__tags.append(tag)

    def unknown_endtag(self, tag):
        self.__tags.pop()
        if self.__data:
            text = string.join(self.__data, "")
            self.__renderer.text(self.__tags, text)
            self.__data = []

class DumbRenderer:
    def __init__(self):
        self.cache = {}

    def text(self, tags, text):
        # render text in the style given by the tag stack
        tags = tuple(tags)
        style = self.cache.get(tags)
        if style is None:
            # figure out a combined style
            style = {}
            for tag in tags:
                s = STYLESHEET.get(tag)
                if s:
                    style.update(s)
            self.cache[tags] = style # update cache
        # write to standard output
        sys.stdout.write("%s =>\n" % style)
        sys.stdout.write("  " + repr(text) + "\n")

#
# try it out
r = DumbRenderer()
c = Parser(r)
c.load(open("samples/sample.xml"))
```
**输出结果**
```
{'style': 'italic'} =>
  'I\'ve had a lot of developers come up to me and\012say, "I haven\'t had this much fun in a long time. It sure
beats\012writing '
{'style': 'italic', 'weight': 'bold'} =>
  'Cobol'
{'style': 'italic'} =>
  '" -- '
{'style': 'italic', 'weight': 'medium'} =>
  'James Gosling'
{'style': 'italic'} =>
  ', on\012'
{'weight': 'bold'} =>
  'Java'
```

---

### 5.3 xml.parsers.expat 模块
(可选) xml.parsers.expat模块是James Clark's Expat XML parser的接口，是一个功能完整且性能很好的语法分析器。

**Example 5-3. 使用 xml.parsers.expat 模块**
File: xml-parsers-expat-example-1.py
```python
from xml.parsers import expat

class Parser:
    def __init__(self):
        self._parser = expat.ParserCreate()
        self._parser.StartElementHandler = self.start
        self._parser.EndElementHandler = self.end
        self._parser.CharacterDataHandler = self.data

    def feed(self, data):
        self._parser.Parse(data, 0)

    def close(self):
        self._parser.Parse("", 1) # end of data
        del self._parser # get rid of circular references

    def start(self, tag, attrs):
        print "START", repr(tag), attrs

    def end(self, tag):
        print "END", repr(tag)

    def data(self, data):
        print "DATA", repr(data)

p = Parser()
p.feed("<tag>data</tag>")
p.close()
```
**输出结果**
```
START u'tag' {}
DATA u'data'
END u'tag'
```

注意：即使你传入的是普通的文本，这里的分析器仍然会返回Unicode字符串。默认情况下，分析器将源文本作为UTF-8解析。如果要使用其他编码，请确保XML文件包含encoding说明。

**Example 5-4. 使用 xml.parsers.expat 模块读取 ISO Latin-1 文本**
File: xml-parsers-expat-example-2.py
```python
from xml.parsers import expat

class Parser:
    def __init__(self):
        self._parser = expat.ParserCreate()
        self._parser.StartElementHandler = self.start
        self._parser.EndElementHandler = self.end
        self._parser.CharacterDataHandler = self.data

    def feed(self, data):
        self._parser.Parse(data, 0)

    def close(self):
        self._parser.Parse("", 1) # end of data
        del self._parser # get rid of circular references

    def start(self, tag, attrs):
        print "START", repr(tag), attrs

    def end(self, tag):
        print "END", repr(tag)

    def data(self, data):
        print "DATA", repr(data)

p = Parser()
p.feed("""\
<?xml version='1.0' encoding='iso-8859-1'?>
<author>
<name>fredrik lundh</name>
<city>linköping</city>
</author>
"""
)
p.close()
```
**输出结果**
```
START u'author' {}
DATA u'\012'
START u'name' {}
DATA u'fredrik lundh'
END u'name'
DATA u'\012'
START u'city' {}
DATA u'link\366ping'
END u'city'
DATA u'\012'
END u'author'
```

---

### 5.4 sgmllib 模块
sgmllib模块提供了一个基本的SGML语法分析器，它与xmllib分析器基本相同，但限制更少(而且不是很完善)。和在xmllib中一样，这个分析器在遇到起始标签、数据区域、结束标签以及实体时调用内部方法。如果你只是对某些标签感兴趣，那么你可以定义特殊的方法。

**Example 5-5. 使用 sgmllib 模块提取 Title 元素**
File: sgmllib-example-1.py
```python
import sgmllib
import string

class FoundTitle(Exception):
    pass

class ExtractTitle(sgmllib.SGMLParser):
    def __init__(self, verbose=0):
        sgmllib.SGMLParser.__init__(self, verbose)
        self.title = self.data = None

    def handle_data(self, data):
        if self.data is not None:
            self.data.append(data)

    def start_title(self, attrs):
        self.data = []

    def end_title(self):
        self.title = string.join(self.data, "")
        raise FoundTitle # abort parsing!

def extract(file):
    # extract title from an HTML/SGML stream
    p = ExtractTitle()
    try:
        while 1:
            # read small chunks
            s = file.read(512)
            if not s:
                break
            p.feed(s)
        p.close()
    except FoundTitle:
        return p.title
    return None

#
# try it out
print "html", "=>", extract(open("samples/sample.htm"))
print "sgml", "=>", extract(open("samples/sample.sgm"))
```
**输出结果**
```
html => A Title.
sgml => Quotations
```

重载`unknown_starttag`和`unknown_endtag`方法就可以处理所有的标签。

**Example 5-6. 使用 sgmllib 模块格式化 SGML 文档**
File: sgmllib-example-2.py
```python
import sgmllib
import cgi, sys

class PrettyPrinter(sgmllib.SGMLParser):
    # A simple SGML pretty printer
    def __init__(self):
        # initialize base class
        sgmllib.SGMLParser.__init__(self)
        self.flag = 0

    def newline(self):
        # force newline, if necessary
        if self.flag:
            sys.stdout.write("\n")
            self.flag = 0

    def unknown_starttag(self, tag, attrs):
        # called for each start tag
        # the attrs argument is a list of (attr, value)
        # tuples. convert it to a string.
        text = ""
        for attr, value in attrs:
            text = text + " %s='%s'" % (attr, cgi.escape(value))
        self.newline()
        sys.stdout.write("<%s%s>\n" % (tag, text))

    def handle_data(self, text):
        # called for each text section
        sys.stdout.write(text)
        self.flag = (text[-1:] != "\n")

    def handle_entityref(self, text):
        # called for each entity
        sys.stdout.write("&%s;" % text)

    def unknown_endtag(self, tag):
        # called for each end tag
        self.newline()
        sys.stdout.write("<%s>" % tag)

#
# try it out
file = open("samples/sample.sgm")
p = PrettyPrinter()
p.feed(file.read())
p.close()
```
**输出结果**
```
<chapter>
<title>
Quotations
<title>
<epigraph>
<attribution>
eff-bot, June 1997
<attribution>
<para>
Nobody expects the Spanish Inquisition! Amongst our weaponry are
such diverse elements as fear, surprise, ruthless efficiency,
and an almost fanatical devotion to <quote>
Guido, and nice red uniforms &mdash; oh, damn!
<quote>
<para>
<epigraph>
<chapter>
```

Example 5-7检查SGML文档是否是如XML那样 "正确格式化"，所有的元素是否正确嵌套，起始和结束标签是否匹配等。我们使用列表保存所有起始标签，然后检查每个结束标签是否匹配前个起始标签，最后确认到达文件末尾时没有未关闭的标签。

**Example 5-7. 使用 sgmllib 模块检查格式**
File: sgmllib-example-3.py
```python
import sgmllib

class WellFormednessChecker(sgmllib.SGMLParser):
    # check that an SGML document is 'well-formed'
    # (in the XML sense).
    def __init__(self, file=None):
        sgmllib.SGMLParser.__init__(self)
        self.tags = []
        if file:
            self.load(file)

    def load(self, file):
        while 1:
            s = file.read(8192)
            if not s:
                break
            self.feed(s)
        self.close()

    def close(self):
        sgmllib.SGMLParser.close(self)
        if self.tags:
            raise SyntaxError, "start tag %s not closed" % self.tags[-1]

    def unknown_starttag(self, start, attrs):
        self.tags.append(start)

    def unknown_endtag(self, end):
        start = self.tags.pop()
        if end != start:
            raise SyntaxError, "end tag %s does't match start tag %s" %\
                (end, start)

try:
    c = WellFormednessChecker()
    c.load(open("samples/sample.htm"))
except SyntaxError:
    raise # report error
else:
    print "document is well-formed"
```
**输出结果**
```
Traceback (innermost last):
  File "sgmllib-example-3.py", line 37, in ?
    c.load(open("samples/sample.htm"))
  File "sgmllib-example-3.py", line 16, in load
    self.feed(s)
  File "/usr/local/lib/python1.5/sgmllib.py", line 91, in feed
    self.goahead(0)
  File "/usr/local/lib/python1.5/sgmllib.py", line 129, in goahead
    self.finish_endtag(tag)
  File "/usr/local/lib/python1.5/sgmllib.py", line 170, in finish_endtag
    self.unknown_endtag(tag)
  File "sgmllib-example-3.py", line 27, in unknown_endtag
    raise SyntaxError, "end tag %s does't match start tag %s" %\
SyntaxError: end tag head does't match start tag meta
```

最后，Example 5-8中的类可以用来过滤HTML和SGML文档，继承这个类，然后实现start和end方法即可。

**Example 5-8. 使用 sgmllib 模块过滤 SGML 文档**
File: sgmllib-example-4.py
```python
import sgmllib
import cgi, string, sys

class SGMLFilter(sgmllib.SGMLParser):
    # sgml filter. override start/end to manipulate
    # document elements
    def __init__(self, outfile=None, infile=None):
        sgmllib.SGMLParser.__init__(self)
        if not outfile:
            outfile = sys.stdout
        self.write = outfile.write
        if infile:
            self.load(infile)

    def load(self, file):
        while 1:
            s = file.read(8192)
            if not s:
                break
            self.feed(s)
        self.close()

    def handle_entityref(self, name):
        self.write("&%s;" % name)

    def handle_data(self, data):
        self.write(cgi.escape(data))

    def unknown_starttag(self, tag, attrs):
        tag, attrs = self.start(tag, attrs)
        if tag:
            if not attrs:
                self.write("<%s>" % tag)
            else:
                self.write("<%s" % tag)
                for k, v in attrs:
                    self.write(" %s=%s" % (k, repr(v)))
                self.write(">")

    def unknown_endtag(self, tag):
        tag = self.end(tag)
        if tag:
            self.write("</%s>" % tag)

    def start(self, tag, attrs):
        return tag, attrs # override

    def end(self, tag):
        return tag # override

class Filter(SGMLFilter):
    def fixtag(self, tag):
        if tag == "em":
            tag = "i"
        if tag == "string":
            tag = "b"
        return string.upper(tag)

    def start(self, tag, attrs):
        return self.fixtag(tag), attrs

    def end(self, tag):
        return self.fixtag(tag)

c = Filter()
c.load(open("samples/sample.htm"))
```

---

### 5.5 htmllib 模块
htmlib模块包含了一个标签驱动的( tag-driven ) HTML语法分析器，它会将数据发送至一个格式化对象。更多关于如何解析HTML的例子请参阅formatter模块。

**Example 5-9. 使用 htmllib 模块**
File: htmllib-example-1.py
```python
import htmllib
import formatter
import string

class Parser(htmllib.HTMLParser):
    # return a dictionary mapping anchor texts to lists
    # of associated hyperlinks
    def __init__(self, verbose=0):
        self.anchors = {}
        f = formatter.NullFormatter()
        htmllib.HTMLParser.__init__(self, f, verbose)

    def anchor_bgn(self, href, name, type):
        self.save_bgn()
        self.anchor = href

    def anchor_end(self):
        text = string.strip(self.save_end())
        if self.anchor and text:
            self.anchors[text] = self.anchors.get(text, []) + [self.anchor]

file = open("samples/sample.htm")
html = file.read()
file.close()

p = Parser()
p.feed(html)
p.close()

for k, v in p.anchors.items():
    print k, "=>", v
print
```
**输出结果**
```
link => ['http://www.python.org']
```

> 注意：如果你只是想解析一个HTML文件，而不是将它交给输出设备，那么sgmllib模块会是更好的选择。

---

### 5.6 htmlentitydefs 模块
htmlentitydefs模块包含一个由HTML中ISO Latin-1字符实体构成的字典。

**Example 5-10. 使用 htmlentitydefs 模块**
File: htmlentitydefs-example-1.py
```python
import htmlentitydefs

entities = htmlentitydefs.entitydefs
for entity in "amp", "quot", "copy", "yen":
    print entity, "=", entities[entity]
```
**输出结果**
```
amp = &
quot = "
copy = \302\251
yen = \302\245
```

Example 5-11展示了如何将正则表达式与这个字典结合起来翻译字符串中的实体 ( cgi.escape 的逆向操作)。

**Example 5-11. 使用 htmlentitydefs 模块翻译实体**
File: htmlentitydefs-example-2.py
```python
import htmlentitydefs
import re
import cgi

pattern = re.compile("&(\w+?);")

def descape_entity(m, defs=htmlentitydefs.entitydefs):
    # callback: translate one entity to its ISO Latin value
    try:
        return defs[m.group(1)]
    except KeyError:
        return m.group(0) # use as is

def descape(string):
    return pattern.sub(descape_entity, string)

print descape("&lt;spam&amp;eggs&gt;")
print descape(cgi.escape("<spam&eggs>"))
```
**输出结果**
```
<spam&eggs>
<spam&eggs>
```

最后，Example 5-12展示了如何将XML保留字符和ISO Latin-1字符转换为XML字符串，与cgi.escape相似，但它会替换非ASCII字符。

**Example 5-12. 转义 ISO Latin-1 实体**
File: htmlentitydefs-example-3.py
```python
import htmlentitydefs
import re, string

# this pattern matches substrings of reserved and non-ASCII characters
pattern = re.compile(r"[&<>\"\x80-\xff]+")

# create character map
entity_map = {}

for i in range(256):
    entity_map[chr(i)] = "&%d;" % i

for entity, char in htmlentitydefs.entitydefs.items():
    if entity_map.has_key(char):
        entity_map[char] = "&%s;" % entity

def escape_entity(m, get=entity_map.get):
    return string.join(map(get, m.group()), "")

def escape(string):
    return pattern.sub(escape_entity, string)

print escape("<spam&eggs>")
print escape("\303\245 i \303\245a \303\244 e \303\266")
```
**输出结果**
```
&lt;spam&amp;eggs&gt;
&aring; i &aring;a &auml; e &ouml;
```

---

### 5.7 formatter 模块
formatter模块提供了一些可用于htmllib的格式类( formatter classes )。这些类有两种：formatter和writer。formatter将HTML解析器的标签和数据流转换为适合输出设备的事件流( event stream )，而writer将事件流输出到设备上。

大多情况下，你可以使用AbstractFormatter类进行格式化，它会根据不同的格式化事件调用writer对象的方法。AbstractWriter类在每次方法调用时打印一条信息。

**Example 5-13. 使用 formatter 模块将 HTML 转换为事件流**
File: formatter-example-1.py
```python
import formatter
import htmllib

w = formatter.AbstractWriter()
f = formatter.AbstractFormatter(w)

file = open("samples/sample.htm")

p = htmllib.HTMLParser(f)
p.feed(file.read())
p.close()

file.close()
```
**输出结果**
```
send_paragraph(1)
new_font(('h1', 0, 1, 0))
send_flowing_data('A Chapter.')
send_line_break()
send_paragraph(1)
new_font(None)
send_flowing_data('Some text. Some more text. Some')
new_font((None, 1, None, None))
send_flowing_data('emphasized')
send_flowing_data(' ')
new_font(None)
send_flowing_data(' text. A')
send_flowing_data(' link')
send_flowing_data('[1]')
send_flowing_data('.')
```

formatter模块还提供了NullWriter类，它会将任何传递给它的事件忽略；以及DumbWriter类，它会将事件流转换为纯文本文档。

**Example 5-14. 使用 formatter 模块将 HTML 转换为纯文本**
File: formatter-example-2.py
```python
import formatter
import htmllib

w = formatter.DumbWriter() # plain text
f = formatter.AbstractFormatter(w)

file = open("samples/sample.htm")

# print html body as plain text
p = htmllib.HTMLParser(f)
p.feed(file.read())
p.close()

file.close()

# print links
print
print
i = 1
for link in p.anchorlist:
    print i, "=>", link
    i = i + 1
```
**输出结果**
```
A Chapter.

Some text. Some more text. Some emphasized text. A link[1].

1 => http://www.python.org
```

Example 5-15提供了一个自定义的Writer，它继承自DumbWriter类，会记录当前字体样式并根据字体美化输出格式。

**Example 5-15. 使用 formatter 模块自定义 Writer**
File: formatter-example-3.py
```python
import formatter
import htmllib, string

class Writer(formatter.DumbWriter):
    def __init__(self):
        formatter.DumbWriter.__init__(self)
        self.tag = ""
        self.bold = self.italic = 0
        self.fonts = []

    def new_font(self, font):
        if font is None:
            font = self.fonts.pop()
            self.tag, self.bold, self.italic = font
        else:
            self.fonts.append((self.tag, self.bold, self.italic))
            tag, bold, italic, typewriter = font
            if tag is not None:
                self.tag = tag
            if bold is not None:
                self.bold = bold
            if italic is not None:
                self.italic = italic

    def send_flowing_data(self, data):
        if not data:
            return
        atbreak = self.atbreak or data[0] in string.whitespace
        for word in string.split(data):
            if atbreak:
                self.file.write(" ")
            if self.tag in ("h1", "h2", "h3"):
                word = string.upper(word)
            if self.bold:
                word = "*" + word + "*"
            if self.italic:
                word = "_" + word + "_"
            self.file.write(word)
            atbreak = 1
        self.atbreak = data[-1] in string.whitespace

w = Writer()
f = formatter.AbstractFormatter(w)

file = open("samples/sample.htm")

# print html body as plain text
p = htmllib.HTMLParser(f)
p.feed(file.read())
p.close()
```
**输出结果**
```
_A_ _CHAPTER._

Some text. Some more text. Some *emphasized* text. A link[1].
```

---

### 5.8 ConfigParser 模块
ConfigParser模块用于读取配置文件，配置文件的格式与Windows INI文件类似，可以包含一个或多个区域 ( section )，每个区域可以有多个配置条目。

样例配置文件（sample.ini）：
```ini
[book]
title: The Python Standard Library
author: Fredrik Lundh
email: fredrik@pythonware.com
version: 2.0-001115

[ematter]
pages: 250

[hardcopy]
pages: 350
```

**Example 5-16. 使用 ConfigParser 模块**
File: configparser-example-1.py
```python
import ConfigParser
import string

config = ConfigParser.ConfigParser()
config.read("samples/sample.ini")

# print summary
print
print string.upper(config.get("book", "title"))
print "by", config.get("book", "author"),
print "(" + config.get("book", "email") + ")"
print
print config.get("ematter", "pages"), "pages"
print

# dump entire config file
for section in config.sections():
    print section
    for option in config.options(section):
        print "  ", option, "=", config.get(section, option)
```
**输出结果**
```
THE PYTHON STANDARD LIBRARY
by Fredrik Lundh (fredrik@pythonware.com)

250 pages

book
  title = The Python Standard Library
  email = fredrik@pythonware.com
  author = Fredrik Lundh
  version = 2.0-001115
  __name__ = book
ematter
  pages = 250
  __name__ = ematter
hardcopy
  pages = 350
  __name__ = hardcopy
```

Python 2.0以后，ConfigParser模块也可以将配置数据写入文件。

**Example 5-17. 使用 ConfigParser 模块写入配置数据**
File: configparser-example-2.py
```python
import ConfigParser
import sys

config = ConfigParser.ConfigParser()

# set a number of parameters
config.add_section("book")
config.set("book", "title", "the python standard library")
config.set("book", "author", "fredrik lundh")

config.add_section("ematter")
config.set("ematter", "pages", 250)

# write to screen
config.write(sys.stdout)
```
**输出结果**
```
[book]
title = the python standard library
author = fredrik lundh

[ematter]
pages = 250
```

---

### 5.9 netrc 模块
netrc模块可以用来解析.netrc配置文件，该文件用于在用户的home目录储存FTP用户名和密码。(别忘记设置这个文件的属性为: "chmod 0600 ~/.netrc," 这样只有当前用户能访问)。

**Example 5-18. 使用 netrc 模块**
File: netrc-example-1.py
```python
import netrc

# default is $HOME/.netrc
info = netrc.netrc("samples/sample.netrc")

login, account, password = info.authenticators("secret.fbi")

print "login", "=>", repr(login)
print "account", "=>", repr(account)
print "password", "=>", repr(password)
```
**输出结果**
```
login => 'mulder'
account => None
password => 'trustno1'
```

---

### 5.10 shlex 模块
shlex模块为基于Unix shell语法的语言提供了一个简单的lexer (也就是tokenizer)。

**Example 5-19. 使用 shlex 模块**
File: shlex-example-1.py
```python
import shlex

lexer = shlex.shlex(open("samples/sample.netrc", "r"))
lexer.wordchars = lexer.wordchars + "._"

while 1:
    token = lexer.get_token()
    if not token:
        break
    print repr(token)
```
**输出结果**
```
'machine'
'secret.fbi'
'login'
'mulder'
'password'
'trustno1'
'machine'
'non.secret.fbi'
'login'
'scully'
'password'
'noway'
```

---

### 5.11 zipfile 模块
(2.0新增) zipfile模块可以用来读写ZIP格式。

#### 5.11.1 列出内容
使用`namelist`和`infolist`方法可以列出压缩档的内容，前者返回由文件名组成的列表，后者返回由ZipInfo实例组成的列表。

**Example 5-20. 使用 zipfile 模块列出 ZIP 文档中的文件**
File: zipfile-example-1.py
```python
import zipfile

file = zipfile.ZipFile("samples/sample.zip", "r")

# list filenames
for name in file.namelist():
    print name,
print

# list file information
for info in file.infolist():
    print info.filename, info.date_time, info.file_size
```
**输出结果**
```
sample.txt sample.jpg
sample.txt (1999, 9, 11, 20, 11, 8) 302
sample.jpg (1999, 9, 18, 16, 9, 44) 4762
```

#### 5.11.2 从 ZIP 文件中读取数据
调用`read`方法就可以从ZIP文档中读取数据，它接受一个文件名作为参数，返回字符串。

**Example 5-21. 使用 zipfile 模块从 ZIP 文件中读取数据**
File: zipfile-example-2.py
```python
import zipfile

file = zipfile.ZipFile("samples/sample.zip", "r")

for name in file.namelist():
    data = file.read(name)
    print name, len(data), repr(data[:10])
```
**输出结果**
```
sample.txt 302 'We will pe'
sample.jpg 4762 '\377\330\377\340\000\020JFIF'
```

#### 5.11.3 向 ZIP 文件写入数据
向压缩档加入文件很简单，将文件名、文件在ZIP档中的名称传递给`write`方法即可。Example 5-22将samples目录中的所有文件打包为一个ZIP文件。

**Example 5-22. 使用 zipfile 模块将文件储存在 ZIP 文件里**
File: zipfile-example-3.py
```python
import zipfile
import glob, os

# open the zip file for writing, and write stuff to it

file = zipfile.ZipFile("test.zip", "w")

for name in glob.glob("samples/*"):
    file.write(name, os.path.basename(name), zipfile.ZIP_DEFLATED)

file.close()

# open the file again, to see what's in it
file = zipfile.ZipFile("test.zip", "r")
for info in file.infolist():
    print info.filename, info.date_time, info.file_size, info.compress_size
```
**输出结果**
```
sample.wav (1999, 8, 15, 21, 26, 46) 13260 10985
sample.jpg (1999, 9, 18, 16, 9, 44) 4762 4626
sample.au (1999, 7, 18, 20, 57, 34) 1676 1103
...
```

`write`方法的第三个可选参数用于控制是否使用压缩，默认为`zipfile.ZIP_STORED`，意味着只是将数据储存在档案里而不进行任何压缩。如果安装了zlib模块，那么就可以使用`zipfile.ZIP_DEFLATED`进行压缩。

zipfile模块也可以向档案中添加字符串，不过这需要你创建一个ZipInfo实例，并正确配置它，Example 5-23提供了一种简单的解决办法。

**Example 5-23. 使用 zipfile 模块在 ZIP 文件中储存字符串**
File: zipfile-example-4.py
```python
import zipfile
import glob, os, time

file = zipfile.ZipFile("test.zip", "w")

now = time.localtime(time.time())[:6]

for name in ("life", "of", "brian"):
    info = zipfile.ZipInfo(name)
    info.date_time = now
    info.compress_type = zipfile.ZIP_DEFLATED
    file.writestr(info, name*1000)

file.close()

# open the file again, to see what's in it
file = zipfile.ZipFile("test.zip", "r")
for info in file.infolist():
    print info.filename, info.date_time, info.file_size, info.compress_size
```
**输出结果**
```
life (2000, 12, 1, 0, 12, 1) 4000 26
of (2000, 12, 1, 0, 12, 1) 2000 18
brian (2000, 12, 1, 0, 12, 1) 5000 31
```

---

### 5.12 gzip 模块
gzip模块用来读写gzip格式的压缩文件。

**Example 5-24. 使用 gzip 模块读取压缩文件**
File: gzip-example-1.py
```python
import gzip

file = gzip.GzipFile("samples/sample.gz")
print file.read()
```
**输出结果**
```
Well it certainly looks as though we're in for a
splendid afternoon's sport in this the 127th
Upperclass Twit of the Year Show.
```

标准的实现并不支持seek和tell方法，不过Example 5-25可以解决这个问题。

**Example 5-25. 给 gzip 模块添加 seek/tell 支持**
File: gzip-example-2.py
```python
import gzip

class gzipFile(gzip.GzipFile):
    # adds seek/tell support to GzipFile
    offset = 0

    def read(self, size=None):
        data = gzip.GzipFile.read(self, size)
        self.offset = self.offset + len(data)
        return data

    def seek(self, offset, whence=0):
        # figure out new position (we can only seek forwards)
        if whence == 0:
            position = offset
        elif whence == 1:
            position = self.offset + offset
        else:
            raise IOError, "Illegal argument"
        if position < self.offset:
            raise IOError, "Cannot seek backwards"

        # skip forward, in 16k blocks
        while position > self.offset:
            if not self.read(min(position - self.offset, 16384)):
                break

    def tell(self):
        return self.offset

#
# try it
file = gzipFile("samples/sample.gz")
file.seek(80)
print file.read()
```
**输出结果**
```
this the 127th
Upperclass Twit of the Year Show.
```

---

## 6. 邮件和新闻消息处理
> 引言："To be removed from our list of future commercial postings by [SOME] PUBLISHING COMPANY