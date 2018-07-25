clc;
clear;

Pose = importdata('ski.txt');

%        1
%        2
%      3   6
%    4       7
%  5           8
%      9   12
%     10   13
%     11   14

Link = [
    1 2;
    2 3;
    3 4;
    4 5;
    2 6;
    6 7;
    7 8;
    2 9;
    9 10;
    10 11;
    2 12;
    12 13;
    13 14
];

for k = 1:size(Pose,1)
    
    X = Pose(k,2:2:end)';
    Y = Pose(k,1:2:end)';
    X = X(1:14,:);
    Y = Y(1:14,:);
    figure(1);
    imshow(ones(300,300),[]);
    hold on;
    plot(X,Y,'go');
    for m = 1:size(Link,1)
        hold on;
        line([X(Link(m,1),1) X(Link(m,2),1)],[Y(Link(m,1),1) Y(Link(m,2),1)],'color','r');
    end
end